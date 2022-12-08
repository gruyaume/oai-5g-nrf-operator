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

    @patch("ops.model.Container.push")
    def test_given_config_file_is_written_when_config_changed_then_pebble_plan_is_created(self, _):
        self.harness.set_can_connect(container="nrf", val=True)
        expected_plan = {
            "services": {
                "nrf": {
                    "override": "replace",
                    "summary": "nrf",
                    "command": "/openair-nrf/bin/oai_nrf -c /openair-nrf/etc/nrf.conf -o",
                    "startup": "enabled",
                }
            },
        }
        self.harness.update_config({"nrfInterfaceNameForSBI": "eth0"})

        updated_plan = self.harness.get_container_pebble_plan("nrf").to_dict()
        service = self.harness.model.unit.get_container("nrf").get_service("nrf")
        self.assertEqual(expected_plan, updated_plan)
        self.assertTrue(service.is_running())
        self.assertEqual(self.harness.model.unit.status, ActiveStatus())

    @patch("ops.model.Container.push")
    def test_given_config_file_is_written_when_config_changed_then_config_file_is_pushed(
        self, mock_push
    ):
        self.harness.set_can_connect(container="nrf", val=True)

        self.harness.update_config({"nrfInterfaceNameForSBI": "eth0"})

        mock_push.assert_called_with(
            path="/openair-nrf/etc/nrf.conf",
            source="################################################################################\n"  # noqa: E501, W505
            "# Licensed to the OpenAirInterface (OAI) Software Alliance under one or more\n"
            "# contributor license agreements.  See the NOTICE file distributed with\n"
            "# this work for additional information regarding copyright ownership.\n"
            "# The OpenAirInterface Software Alliance licenses this file to You under\n"
            '# the OAI Public License, Version 1.1  (the "License"); you may not use this file\n'  # noqa: E501, W505
            "# except in compliance with the License.\n"
            "# You may obtain a copy of the License at\n"
            "#\n"
            "#      http://www.openairinterface.org/?page_id=698\n"
            "#\n"
            "# Unless required by applicable law or agreed to in writing, software\n"
            '# distributed under the License is distributed on an "AS IS" BASIS,\n'
            "# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.\n"
            "# See the License for the specific language governing permissions and\n"
            "# limitations under the License.\n"
            "#-------------------------------------------------------------------------------\n"  # noqa: E501, W505
            "# For more information about the OpenAirInterface (OAI) Software Alliance:\n"
            "#      contact@openairinterface.org\n"
            "################################################################################\n\n"  # noqa: E501, W505
            "NRF =\n"
            "{\n"
            "    INSTANCE      = 0;         # 0 is the default\n"
            '    PID_DIRECTORY = "/var/run";  # /var/run is the default\n\n\n'
            "    SBI_INTERFACE :\n"
            "    {\n"
            "        # NRF binded interface for SBI interface (e.g., communication with other NFs e.g., AMF, SMF, UDM)\n"  # noqa: E501, W505
            '        INTERFACE_NAME = "eth0";     # YOUR NETWORK CONFIG HERE\n'
            '        IPV4_ADDRESS   = "read";\n'
            "        PORT           = 80;       # YOUR NETWORK CONFIG HERE (default: 80)\n"
            "        HTTP2_PORT     = 9090; # YOUR NETWORK CONFIG HERE\n"
            '        API_VERSION    = "v1";                # YOUR NRF API VERSION CONFIG HERE\n'  # noqa: E501, W505
            "    };\n\n"
            "};\n",
        )

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
