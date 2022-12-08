#!/usr/bin/env python3
# Copyright 2022 Guillaume Belanger
# See LICENSE file for licensing details.

"""Charmed Operator for the OpenAirInterface 5G Core NRF component."""


import logging

from charms.observability_libs.v1.kubernetes_service_patch import (  # type: ignore[import]
    KubernetesServicePatch,
    ServicePort,
)
from jinja2 import Environment, FileSystemLoader
from ops.charm import CharmBase, ConfigChangedEvent, PebbleReadyEvent
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
        self._container_name = "nrf"
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
        self.framework.observe(self.on.nrf_pebble_ready, self._on_nrf_pebble_ready)
        self.framework.observe(self.on.config_changed, self._on_config_changed)

    def _on_nrf_pebble_ready(self, event: PebbleReadyEvent) -> None:
        """Triggered on Pebble Ready Event.

        Args:
            event: Pebble Ready Event

        Returns:
            None
        """
        if not self._config_file_is_pushed:
            self.unit.status = WaitingStatus("Waiting for config files to be pushed")
            event.defer()
            return
        self._container.add_layer("nrf", self._pebble_layer, combine=True)
        self._container.replan()
        self.unit.status = ActiveStatus()

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
        self._container.replan()
        self.unit.status = ActiveStatus()

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
                "nrf": {
                    "override": "replace",
                    "summary": "nrf",
                    "command": f"/openair-nrf/bin/oai_nrf -c {BASE_CONFIG_PATH}/{CONFIG_FILE_NAME} -o",  # noqa: E501
                    "startup": "enabled",
                    "environment": {
                        "INSTANCE": self._config_instance,
                        "PID_DIRECTORY": self._config_pid_directory,
                        "NRF_INTERFACE_NAME_FOR_SBI": self._config_sbi_interface_name,
                        "NRF_INTERFACE_PORT_FOR_SBI": self._config_sbi_interface_port,
                        "NRF_INTERFACE_HTTP2_PORT_FOR_SBI": self._config_sbi_interface_http2_port,
                        "NRF_API_VERSION": self._config_sbi_interface_nrf_api_version,
                    },
                }
            },
        }


if __name__ == "__main__":
    main(Oai5GNrfOperatorCharm)
