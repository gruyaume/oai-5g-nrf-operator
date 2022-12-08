# Copyright 2022 Guillaume Belanger
# See LICENSE file for licensing details.

import unittest
from unittest.mock import patch

import ops.testing
from ops.model import ActiveStatus
from ops.testing import Harness

from charm import Oai5GNrfOperatorCharm


class TestCharm(unittest.TestCase):
    @patch(
        "charm.KubernetesServicePatch",
        lambda charm, ports: None,
    )
    def setUp(self):
        ops.testing.SIMULATE_CAN_CONNECT = True
        self.addCleanup(setattr, ops.testing, "SIMULATE_CAN_CONNECT", False)
        self.harness = Harness(Oai5GNrfOperatorCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    @patch("ops.model.Container.exists")
    def test_given_config_file_is_written_when_pebble_ready_then_pebble_plan_is_created(
        self, mock_container_exists
    ):
        mock_container_exists.return_value = True
        expected_plan = {
            "services": {
                "nrf": {
                    "override": "replace",
                    "summary": "nrf",
                    "command": "/openair-nrf/bin/oai_nrf -c /openair-nrf/etc/nrf.conf -o",
                    "startup": "enabled",
                    "environment": {
                        "INSTANCE": "0",
                        "PID_DIRECTORY": "/var/run",
                        "NRF_INTERFACE_NAME_FOR_SBI": "eth0",
                        "NRF_INTERFACE_PORT_FOR_SBI": "80",
                        "NRF_INTERFACE_HTTP2_PORT_FOR_SBI": "9090",
                        "NRF_API_VERSION": "v1",
                    },
                }
            },
        }
        self.harness.container_pebble_ready("nrf")
        updated_plan = self.harness.get_container_pebble_plan("nrf").to_dict()
        self.assertEqual(expected_plan, updated_plan)
        service = self.harness.model.unit.get_container("nrf").get_service("nrf")
        self.assertTrue(service.is_running())
        self.assertEqual(self.harness.model.unit.status, ActiveStatus())

    def test_given_unit_is_leader_when_nrf_relation_joined_then_nrf_relation_data_is_set(self):
        self.harness.set_leader(True)

        relation_id = self.harness.add_relation(relation_name="fiveg-nrf", remote_app="udr")
        self.harness.add_relation_unit(relation_id=relation_id, remote_unit_name="udr/0")

        relation_data = self.harness.get_relation_data(
            relation_id=relation_id, app_or_unit=self.harness.model.app.name
        )

        assert relation_data["nrf_ipv4_address"] == "127.0.0.1"
        assert relation_data["nrf_fqdn"] == "oai-5g-nrf.svc.cluster.local"
        assert relation_data["nrf_port"] == "80"
        assert relation_data["nrf_api_version"] == "v1"
