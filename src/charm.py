#!/usr/bin/env python3
# Copyright 2022 Guillaume Belanger
# See LICENSE file for licensing details.

"""Charmed Operator for the OpenAirInterface 5G Core NRF component."""


import logging

from charms.oai_5g_nrf.v0.fiveg_nrf import FiveGNRFProvides  # type: ignore[import]
from charms.observability_libs.v1.kubernetes_service_patch import (  # type: ignore[import]
    KubernetesServicePatch,
    ServicePort,
)
from jinja2 import Environment, FileSystemLoader
from ops.charm import CharmBase, ConfigChangedEvent
from ops.main import main
from ops.model import ActiveStatus, WaitingStatus

logger = logging.getLogger(__name__)

BASE_CONFIG_PATH = "/openair-nrf/etc"
CONFIG_FILE_NAME = "nrf.conf"


class Oai5GNrfOperatorCharm(CharmBase):
    """Charm the service."""

    def __init__(self, *args):
        """Observes juju events."""
        super().__init__(*args)
        self._container_name = self._service_name = "nrf"
        self._container = self.unit.get_container(self._container_name)
        self.service_patcher = KubernetesServicePatch(
            charm=self,
            ports=[
                ServicePort(
                    name="http1",
                    port=int(self._config_sbi_interface_port),
                    protocol="TCP",
                    targetPort=int(self._config_sbi_interface_port),
                ),
                ServicePort(
                    name="http2",
                    port=int(self._config_sbi_interface_http2_port),
                    protocol="TCP",
                    targetPort=int(self._config_sbi_interface_http2_port),
                ),
            ],
        )
        self.nrf_provides = FiveGNRFProvides(self, "fiveg-nrf")
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(
            self.on.fiveg_nrf_relation_joined, self._on_fiveg_nrf_relation_joined
        )

    def _update_pebble_layer(self) -> None:
        """Update Pebble layer configuration.

        Returns:
            None
        """
        self._container.add_layer("nrf", self._pebble_layer, combine=True)
        self._container.replan()
        self._container.restart(self._service_name)

    def _on_config_changed(self, event: ConfigChangedEvent) -> None:
        """Triggered on any change in configuration.

        Args:
            event: Config Changed Event

        Returns:
            None
        """
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for Pebble in workload container")
            event.defer()
            return
        self._push_config()
        self._update_pebble_layer()
        self.unit.status = ActiveStatus()

    def _on_fiveg_nrf_relation_joined(self, event) -> None:
        """Triggered when a relation is joined.

        Args:
            event: Relation Joined Event
        """
        if not self.unit.is_leader():
            return
        if not self._nrf_service_started:
            logger.info("NRF service not started yet, deferring event")
            event.defer()
            return
        if not self._nrf_is_listening:
            logger.info("NRF is not listening yet, deferring event")
            event.defer()
            return
        self.nrf_provides.set_nrf_information(
            nrf_ipv4_address="127.0.0.1",
            nrf_fqdn=f"{self.model.app.name}.{self.model.name}.svc.cluster.local",
            nrf_port=self._config_sbi_interface_port,
            nrf_api_version=self._config_sbi_interface_nrf_api_version,
            relation_id=event.relation.id,
        )

    @property
    def _nrf_service_started(self) -> bool:
        if not self._container.can_connect():
            return False
        if not self._container.get_service(self._service_name).is_running():
            return False
        return True

    @property
    def _nrf_is_listening(self) -> bool:
        # TODO: Check if the NRF is listening on the configured port
        # NRF_IP_SBI_INTERFACE=$(ifconfig $NRF_INTERFACE_NAME_FOR_SBI | grep inet | awk {'print $2'})  # noqa: E501, W505
        # NRF_SBI_PORT_STATUS=$(netstat -tnpl | grep -o "$NRF_IP_SBI_INTERFACE:$NRF_INTERFACE_PORT_FOR_SBI") # noqa: E501, W505
        # if [[ -z $NRF_SBI_PORT_STATUS ]]; then
        # 	STATUS=1
        # 	echo "Healthcheck error: UNHEALTHY SBI TCP/HTTP port $NRF_INTERFACE_PORT_FOR_SBI is not listening." # noqa: E501, W505
        # fi
        return True

    def _push_config(self) -> None:
        jinja2_environment = Environment(loader=FileSystemLoader("src/templates/"))
        template = jinja2_environment.get_template(f"{CONFIG_FILE_NAME}.j2")
        content = template.render(
            instance=self._config_instance,
            pid_directory=self._config_pid_directory,
            sbi_interface_name=self._config_sbi_interface_name,
            sbi_interface_port=self._config_sbi_interface_port,
            sbi_interface_http2_port=self._config_sbi_interface_http2_port,
            sbi_interface_nrf_api_version=self._config_sbi_interface_nrf_api_version,
        )

        self._container.push(path=f"{BASE_CONFIG_PATH}/{CONFIG_FILE_NAME}", source=content)
        logger.info(f"Wrote file to container: {CONFIG_FILE_NAME}")

    @property
    def _config_file_is_pushed(self) -> bool:
        """Check if config file is pushed to the container."""
        if not self._container.exists(f"{BASE_CONFIG_PATH}/{CONFIG_FILE_NAME}"):
            logger.info(f"Config file is not written: {CONFIG_FILE_NAME}")
            return False
        logger.info("Config file is pushed")
        return True

    @property
    def _config_instance(self) -> str:
        return "0"

    @property
    def _config_pid_directory(self) -> str:
        return "/var/run"

    @property
    def _config_sbi_interface_name(self) -> str:
        return self.model.config["nrfInterfaceNameForSBI"]

    @property
    def _config_sbi_interface_port(self) -> str:
        return "80"

    @property
    def _config_sbi_interface_http2_port(self) -> str:
        return "9090"

    @property
    def _config_sbi_interface_nrf_api_version(self) -> str:
        return "v1"

    @property
    def _pebble_layer(self) -> dict:
        """Return a dictionary representing a Pebble layer."""
        return {
            "summary": "nrf layer",
            "description": "pebble config layer for nrf",
            "services": {
                self._service_name: {
                    "override": "replace",
                    "summary": "nrf",
                    "command": f"/openair-nrf/bin/oai_nrf -c {BASE_CONFIG_PATH}/{CONFIG_FILE_NAME} -o",  # noqa: E501
                    "startup": "enabled",
                }
            },
        }


if __name__ == "__main__":
    main(Oai5GNrfOperatorCharm)
