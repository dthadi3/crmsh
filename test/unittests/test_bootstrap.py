"""
Unitary tests for crmsh/bootstrap.py

:author: xinliang
:organization: SUSE Linux GmbH
:contact: XLiang@suse.de

:since: 2019-10-21
"""

# pylint:disable=C0103,C0111,W0212,W0611

import os
import unittest

try:
    from unittest import mock
except ImportError:
    import mock

from crmsh import bootstrap
from crmsh import corosync


class TestWatchdog(unittest.TestCase):
    """
    Unitary tests for crmsh.bootstrap.Watchdog
    """

    @classmethod
    def setUpClass(cls):
        """
        Global setUp.
        """

    def setUp(self):
        """
        Test setUp.
        """
        self.watchdog_inst = bootstrap.Watchdog()
        self.watchdog_join_inst = bootstrap.Watchdog(peer_host="node1")

    def tearDown(self):
        """
        Test tearDown.
        """

    @classmethod
    def tearDownClass(cls):
        """
        Global tearDown.
        """

    @mock.patch('crmsh.utils.get_stdout_stderr')
    def test_verify_watchdog_device_ignore_error(self, mock_run):
        mock_run.return_value = (1, None, "error")
        res = self.watchdog_inst._verify_watchdog_device("/dev/watchdog", True)
        self.assertEqual(res, False)
        mock_run.assert_called_once_with("wdctl /dev/watchdog")

    @mock.patch('crmsh.bootstrap.error')
    @mock.patch('crmsh.utils.get_stdout_stderr')
    def test_verify_watchdog_device_error(self, mock_run, mock_error):
        mock_run.return_value = (1, None, "error")
        mock_error.side_effect = ValueError
        with self.assertRaises(ValueError) as err:
            self.watchdog_inst._verify_watchdog_device("/dev/watchdog")
        mock_error.assert_called_once_with("Invalid watchdog device /dev/watchdog: error")
        mock_run.assert_called_once_with("wdctl /dev/watchdog")

    @mock.patch('crmsh.utils.get_stdout_stderr')
    def test_verify_watchdog_device(self, mock_run):
        mock_run.return_value = (0, None, None)
        res = self.watchdog_inst._verify_watchdog_device("/dev/watchdog")
        self.assertEqual(res, True)

    @mock.patch('crmsh.bootstrap.invoke')
    def test_load_watchdog_driver(self, mock_invoke):
        self.watchdog_inst._load_watchdog_driver("softdog")
        mock_invoke.assert_has_calls([
            mock.call("echo softdog > /etc/modules-load.d/watchdog.conf"),
            mock.call("systemctl restart systemd-modules-load")
            ])

    @mock.patch('crmsh.utils.parse_sysconfig')
    def test_get_watchdog_device_from_sbd_config(self, mock_parse):
        mock_parse_inst = mock.Mock()
        mock_parse.return_value = mock_parse_inst
        mock_parse_inst.get.return_value = "/dev/watchdog"
        res = self.watchdog_inst._get_watchdog_device_from_sbd_config()
        self.assertEqual(res, "/dev/watchdog")
        mock_parse.assert_called_once_with(bootstrap.SYSCONFIG_SBD)

    @mock.patch('crmsh.utils.get_stdout_stderr')
    def test_driver_is_loaded(self, mock_run):
        output = """
button                 24576  0
softdog                16384  2
btrfs                1474560  1
        """
        mock_run.return_value = (0, output, None)
        res = self.watchdog_inst._driver_is_loaded("softdog")
        assert res is not None
        mock_run.assert_called_once_with("lsmod")

    @mock.patch('crmsh.bootstrap.error')
    @mock.patch('crmsh.utils.get_stdout_stderr')
    def test_set_watchdog_info_error(self, mock_run, mock_error):
        mock_run.return_value = (1, None, "error")
        mock_error.side_effect = ValueError
        with self.assertRaises(ValueError):
            self.watchdog_inst._set_watchdog_info()
        mock_run.assert_called_once_with(bootstrap.Watchdog.QUERY_CMD)
        mock_error.assert_called_once_with("Failed to run {}: error".format(bootstrap.Watchdog.QUERY_CMD))

    @mock.patch('crmsh.utils.get_stdout_stderr')
    def test_set_watchdog_info(self, mock_run):
        output = """
Discovered 3 watchdog devices:

[1] /dev/watchdog
Identity: Software Watchdog
Driver: softdog
CAUTION: Not recommended for use with sbd.

[2] /dev/watchdog0
Identity: Software Watchdog
Driver: softdog
CAUTION: Not recommended for use with sbd.

[3] /dev/watchdog1
Identity: iTCO_wdt
Driver: iTCO_wdt
        """
        mock_run.return_value = (0, output, None)
        self.watchdog_inst._set_watchdog_info()
        self.assertEqual(self.watchdog_inst._watchdog_info_dict, {'/dev/watchdog': 'softdog', '/dev/watchdog0': 'softdog', '/dev/watchdog1': 'iTCO_wdt'})

    @mock.patch('crmsh.bootstrap.Watchdog._verify_watchdog_device')
    def test_get_device_through_driver_none(self, mock_verify):
        self.watchdog_inst._watchdog_info_dict = {'/dev/watchdog': 'softdog', '/dev/watchdog0': 'softdog', '/dev/watchdog1': 'iTCO_wdt'}
        mock_verify.return_value = False
        res = self.watchdog_inst._get_device_through_driver("iTCO_wdt")
        self.assertEqual(res, None)
        mock_verify.assert_called_once_with("/dev/watchdog1")

    @mock.patch('crmsh.bootstrap.Watchdog._verify_watchdog_device')
    def test_get_device_through_driver(self, mock_verify):
        self.watchdog_inst._watchdog_info_dict = {'/dev/watchdog': 'softdog', '/dev/watchdog0': 'softdog', '/dev/watchdog1': 'iTCO_wdt'}
        mock_verify.return_value = True
        res = self.watchdog_inst._get_device_through_driver("iTCO_wdt")
        self.assertEqual(res, "/dev/watchdog1")
        mock_verify.assert_called_once_with("/dev/watchdog1")

    @mock.patch('crmsh.bootstrap.error')
    @mock.patch('crmsh.utils.get_stdout_stderr')
    def test_get_driver_through_device_remotely_error(self, mock_run, mock_error):
        mock_run.return_value = (1, None, "error")
        self.watchdog_join_inst._get_driver_through_device_remotely("test")
        mock_run.assert_called_once_with("ssh -o StrictHostKeyChecking=no root@node1 sbd query-watchdog")
        mock_error.assert_called_once_with("Failed to run sbd query-watchdog remotely: error")

    @mock.patch('crmsh.utils.get_stdout_stderr')
    def test_get_driver_through_device_remotely_none(self, mock_run):
        mock_run.return_value = (0, "data", None)
        res = self.watchdog_join_inst._get_driver_through_device_remotely("/dev/watchdog")
        self.assertEqual(res, None)
        mock_run.assert_called_once_with("ssh -o StrictHostKeyChecking=no root@node1 sbd query-watchdog")

    @mock.patch('crmsh.utils.get_stdout_stderr')
    def test_get_driver_through_device_remotely(self, mock_run):
        output = """
Discovered 3 watchdog devices:

[1] /dev/watchdog
Identity: Software Watchdog
Driver: softdog
CAUTION: Not recommended for use with sbd.

[2] /dev/watchdog0
Identity: Software Watchdog
Driver: softdog
CAUTION: Not recommended for use with sbd.

[3] /dev/watchdog1
Identity: iTCO_wdt
Driver: iTCO_wdt
        """
        mock_run.return_value = (0, output, None)
        res = self.watchdog_join_inst._get_driver_through_device_remotely("/dev/watchdog")
        self.assertEqual(res, "softdog")
        mock_run.assert_called_once_with("ssh -o StrictHostKeyChecking=no root@node1 sbd query-watchdog")

    def test_get_first_unused_device_none(self):
        res = self.watchdog_inst._get_first_unused_device()
        self.assertEqual(res, None)

    @mock.patch('crmsh.bootstrap.Watchdog._verify_watchdog_device')
    def test_get_first_unused_device(self, mock_verify):
        mock_verify.return_value = True
        self.watchdog_inst._watchdog_info_dict = {'/dev/watchdog': 'softdog', '/dev/watchdog0': 'softdog', '/dev/watchdog1': 'iTCO_wdt'}
        res = self.watchdog_inst._get_first_unused_device()
        self.assertEqual(res, "/dev/watchdog")
        mock_verify.assert_called_once_with("/dev/watchdog", ignore_error=True)

    @mock.patch('crmsh.bootstrap.Watchdog._get_first_unused_device')
    @mock.patch('crmsh.bootstrap.Watchdog._verify_watchdog_device')
    @mock.patch('crmsh.bootstrap.Watchdog._get_watchdog_device_from_sbd_config')
    def test_set_input_from_config(self, mock_from_config, mock_verify, mock_first):
        mock_from_config.return_value = "/dev/watchdog"
        mock_verify.return_value = True
        self.watchdog_inst._set_input()
        mock_first.assert_not_called()
        mock_from_config.assert_called_once_with()

    @mock.patch('crmsh.bootstrap.Watchdog._get_first_unused_device')
    @mock.patch('crmsh.bootstrap.Watchdog._verify_watchdog_device')
    @mock.patch('crmsh.bootstrap.Watchdog._get_watchdog_device_from_sbd_config')
    def test_set_input(self, mock_from_config, mock_verify, mock_first):
        mock_from_config.return_value = None
        mock_first.return_value = None
        self.watchdog_inst._set_input()
        self.assertEqual(self.watchdog_inst._input, "softdog")
        mock_from_config.assert_called_once_with()
        mock_verify.assert_not_called()
        mock_first.assert_called_once_with()

    def test_valid_device_false(self):
        res = self.watchdog_inst._valid_device("test")
        self.assertEqual(res, False)

    @mock.patch('crmsh.bootstrap.Watchdog._verify_watchdog_device')
    def test_valid_device(self, mock_verify):
        mock_verify.return_value = True
        self.watchdog_inst._watchdog_info_dict = {'/dev/watchdog': 'softdog', '/dev/watchdog0': 'softdog', '/dev/watchdog1': 'iTCO_wdt'}
        res = self.watchdog_inst._valid_device("/dev/watchdog")
        self.assertEqual(res, True)

    @mock.patch('crmsh.bootstrap.error')
    @mock.patch('crmsh.bootstrap.Watchdog._get_watchdog_device_from_sbd_config')
    @mock.patch('crmsh.bootstrap.Watchdog._set_watchdog_info')
    def test_join_watchdog_error(self, mock_set_info, mock_from_config, mock_error):
        mock_from_config.return_value = None
        mock_error.side_effect = SystemExit
        with self.assertRaises(SystemExit):
            self.watchdog_join_inst.join_watchdog()
        mock_set_info.assert_called_once_with()
        mock_from_config.assert_called_once_with()
        mock_error.assert_called_once_with("Failed to get watchdog device from {}".format(bootstrap.SYSCONFIG_SBD))

    @mock.patch('crmsh.bootstrap.Watchdog._load_watchdog_driver')
    @mock.patch('crmsh.bootstrap.Watchdog._get_driver_through_device_remotely')
    @mock.patch('crmsh.bootstrap.Watchdog._valid_device')
    @mock.patch('crmsh.bootstrap.Watchdog._get_watchdog_device_from_sbd_config')
    @mock.patch('crmsh.bootstrap.Watchdog._set_watchdog_info')
    def test_join_watchdog(self, mock_set_info, mock_from_config, mock_valid, mock_get_driver_remotely, mock_load):
        mock_from_config.return_value = "/dev/watchdog"
        mock_valid.return_value = False
        mock_get_driver_remotely.return_value = "softdog"

        self.watchdog_join_inst.join_watchdog()

        mock_set_info.assert_called_once_with()
        mock_from_config.assert_called_once_with()
        mock_valid.assert_called_once_with("/dev/watchdog")
        mock_get_driver_remotely.assert_called_once_with("/dev/watchdog")
        mock_load.assert_called_once_with("softdog")

    @mock.patch('crmsh.bootstrap.invokerc')
    @mock.patch('crmsh.bootstrap.Watchdog._valid_device')
    @mock.patch('crmsh.bootstrap.Watchdog._set_input')
    @mock.patch('crmsh.bootstrap.Watchdog._set_watchdog_info')
    def test_init_watchdog_valid(self, mock_set_info, mock_set_input, mock_valid, mock_invokerc):
        mock_valid.return_value = True
        self.watchdog_inst._input = "/dev/watchdog"
        self.watchdog_inst.init_watchdog()
        mock_invokerc.assert_not_called()
        mock_valid.assert_called_once_with("/dev/watchdog")

    @mock.patch('crmsh.bootstrap.error')
    @mock.patch('crmsh.bootstrap.invokerc')
    @mock.patch('crmsh.bootstrap.Watchdog._valid_device')
    @mock.patch('crmsh.bootstrap.Watchdog._set_input')
    @mock.patch('crmsh.bootstrap.Watchdog._set_watchdog_info')
    def test_init_watchdog_error(self, mock_set_info, mock_set_input, mock_valid, mock_invokerc, mock_error):
        mock_valid.return_value = False
        mock_invokerc.return_value = False
        self.watchdog_inst._input = "test"
        mock_error.side_effect = SystemExit

        with self.assertRaises(SystemExit):
            self.watchdog_inst.init_watchdog()

        mock_valid.assert_called_once_with("test")
        mock_invokerc.assert_called_once_with("modinfo test")
        mock_error.assert_called_once_with("Should provide valid watchdog device or driver name by -w option")

    @mock.patch('crmsh.bootstrap.Watchdog._get_device_through_driver')
    @mock.patch('crmsh.bootstrap.Watchdog._load_watchdog_driver')
    @mock.patch('crmsh.bootstrap.Watchdog._driver_is_loaded')
    @mock.patch('crmsh.bootstrap.invokerc')
    @mock.patch('crmsh.bootstrap.Watchdog._valid_device')
    @mock.patch('crmsh.bootstrap.Watchdog._set_input')
    @mock.patch('crmsh.bootstrap.Watchdog._set_watchdog_info')
    def test_init_watchdog(self, mock_set_info, mock_set_input, mock_valid, mock_invokerc, mock_is_loaded, mock_load, mock_get_device):
        mock_valid.return_value = False
        self.watchdog_inst._input = "softdog"
        mock_invokerc.return_value = True
        mock_is_loaded.return_value = False
        mock_get_device.return_value = "/dev/watchdog"

        self.watchdog_inst.init_watchdog()

        mock_valid.assert_called_once_with("softdog")
        mock_invokerc.assert_called_once_with("modinfo softdog")
        mock_is_loaded.assert_called_once_with("softdog")
        mock_load.assert_called_once_with("softdog")
        mock_set_info.assert_has_calls([mock.call(), mock.call()])
        mock_get_device.assert_called_once_with("softdog")


class TestSBDManager(unittest.TestCase):
    """
    Unitary tests for crmsh.bootstrap.SBDManager
    """

    @classmethod
    def setUpClass(cls):
        """
        Global setUp.
        """

    def setUp(self):
        """
        Test setUp.
        """
        self.sbd_inst = bootstrap.SBDManager(sbd_devices=["/dev/sdb1", "/dev/sdc1"])
        self.sbd_inst_devices_gt_3 = bootstrap.SBDManager(sbd_devices=["/dev/sdb1", "/dev/sdc1", "/dev/sdd1", "/dev/sde1"])
        self.sbd_inst_interactive = bootstrap.SBDManager()
        self.sbd_inst_diskless = bootstrap.SBDManager(diskless_sbd=True)

    def tearDown(self):
        """
        Test tearDown.
        """

    @classmethod
    def tearDownClass(cls):
        """
        Global tearDown.
        """

    @mock.patch('crmsh.bootstrap.warn')
    def test_get_sbd_device_interactive_yes_to_all(self, mock_warn):
        bootstrap._context = mock.Mock(yes_to_all=True)
        self.sbd_inst._get_sbd_device_interactive()
        mock_warn.assert_called_once_with("Not configuring SBD ({} left untouched).".format(bootstrap.SYSCONFIG_SBD))

    @mock.patch('crmsh.bootstrap.confirm')
    @mock.patch('crmsh.bootstrap.status')
    @mock.patch('crmsh.bootstrap.warn')
    def test__get_sbd_device_interactive_not_confirm(self, mock_warn, mock_status, mock_confirm):
        bootstrap._context = mock.Mock(yes_to_all=False)
        mock_confirm.return_value = False
        self.sbd_inst._get_sbd_device_interactive()
        mock_status.assert_called_once_with(bootstrap.SBDManager.SBD_STATUS_DESCRIPTION)
        mock_warn.assert_called_once_with("Not configuring SBD - STONITH will be disabled.")

    @mock.patch('crmsh.bootstrap.SBDManager._get_sbd_device_from_config')
    @mock.patch('crmsh.bootstrap.confirm')
    @mock.patch('crmsh.bootstrap.status')
    def test_get_sbd_device_interactive_already_configured(self, mock_status, mock_confirm, mock_from_config):
        bootstrap._context = mock.Mock(yes_to_all=False)
        mock_confirm.side_effect = [True, False]
        mock_from_config.return_value = ["/dev/sda1"]

        res = self.sbd_inst._get_sbd_device_interactive()
        self.assertEqual(res, ["/dev/sda1"])

        mock_status.assert_called_once_with(bootstrap.SBDManager.SBD_STATUS_DESCRIPTION)
        mock_confirm.assert_has_calls([
            mock.call("Do you wish to use SBD?"),
            mock.call("SBD is already configured to use /dev/sda1 - overwrite?")
            ])
        mock_status.assert_called_once_with(bootstrap.SBDManager.SBD_STATUS_DESCRIPTION)
        mock_from_config.assert_called_once_with()

    @mock.patch('crmsh.bootstrap.prompt_for_string')
    @mock.patch('crmsh.bootstrap.SBDManager._get_sbd_device_from_config')
    @mock.patch('crmsh.bootstrap.confirm')
    @mock.patch('crmsh.bootstrap.status')
    def test_get_sbd_device_interactive_diskless(self, mock_status, mock_confirm, mock_from_config, mock_prompt):
        bootstrap._context = mock.Mock(yes_to_all=False)
        mock_confirm.return_value = True
        mock_from_config.return_value = None
        mock_prompt.return_value = "none"

        self.sbd_inst._get_sbd_device_interactive()

        mock_status.assert_called_once_with(bootstrap.SBDManager.SBD_STATUS_DESCRIPTION)
        mock_from_config.assert_called_once_with()
        mock_prompt.assert_called_once_with('Path to storage device (e.g. /dev/disk/by-id/...), or "none" for diskless sbd, use ";" as separator for multi path', 'none|\\/.*')

    @mock.patch('crmsh.bootstrap.prompt_for_string')
    @mock.patch('crmsh.bootstrap.SBDManager._get_sbd_device_from_config')
    @mock.patch('crmsh.bootstrap.confirm')
    @mock.patch('crmsh.bootstrap.status')
    def test_get_sbd_device_interactive_null_and_diskless(self, mock_status, mock_confirm, mock_from_config, mock_prompt):
        bootstrap._context = mock.Mock(yes_to_all=False)
        mock_confirm.return_value = True
        mock_from_config.return_value = None
        mock_prompt.side_effect = [None, "none"]

        self.sbd_inst._get_sbd_device_interactive()

        mock_status.assert_called_once_with(bootstrap.SBDManager.SBD_STATUS_DESCRIPTION)
        mock_confirm.assert_called_once_with("Do you wish to use SBD?")
        mock_from_config.assert_called_once_with()
        mock_prompt.assert_has_calls([
            mock.call('Path to storage device (e.g. /dev/disk/by-id/...), or "none" for diskless sbd, use ";" as separator for multi path', 'none|\\/.*') for x in range(2)
            ])

    @mock.patch('crmsh.bootstrap.warn')
    @mock.patch('crmsh.bootstrap.print_error_msg')
    @mock.patch('crmsh.bootstrap.SBDManager._verify_sbd_device')
    @mock.patch('crmsh.bootstrap.prompt_for_string')
    @mock.patch('crmsh.bootstrap.SBDManager._get_sbd_device_from_config')
    @mock.patch('crmsh.bootstrap.confirm')
    @mock.patch('crmsh.bootstrap.status')
    def test_get_sbd_device_interactive(self, mock_status, mock_confirm, mock_from_config, mock_prompt, mock_verify, mock_error_msg, mock_warn):
        bootstrap._context = mock.Mock(yes_to_all=False)
        mock_confirm.side_effect = [True, False, True]
        mock_from_config.return_value = None
        mock_prompt.side_effect = ["/dev/test1", "/dev/sda1", "/dev/sdb1"]
        mock_verify.side_effect = [ValueError("/dev/test1 error"), None, None]

        res = self.sbd_inst._get_sbd_device_interactive()
        self.assertEqual(res, ["/dev/sdb1"])

        mock_status.assert_called_once_with(bootstrap.SBDManager.SBD_STATUS_DESCRIPTION)
        mock_confirm.assert_has_calls([
            mock.call("Do you wish to use SBD?"),
            mock.call("Are you sure you wish to use this device?")
            ])
        mock_from_config.assert_called_once_with()
        mock_error_msg.assert_called_once_with("/dev/test1 error")
        mock_warn.assert_has_calls([
            mock.call("All data on /dev/sda1 will be destroyed!"),
            mock.call("All data on /dev/sdb1 will be destroyed!")
            ])
        mock_prompt.assert_has_calls([
            mock.call('Path to storage device (e.g. /dev/disk/by-id/...), or "none" for diskless sbd, use ";" as separator for multi path', 'none|\\/.*') for x in range(3)
            ])

    def test_parse_sbd_device(self):
        res = self.sbd_inst._parse_sbd_device()
        assert res == ["/dev/sdb1", "/dev/sdc1"]

    def test_verify_sbd_device_gt_3(self):
        assert self.sbd_inst_devices_gt_3.sbd_devices_input == ["/dev/sdb1", "/dev/sdc1", "/dev/sdd1", "/dev/sde1"]
        dev_list = self.sbd_inst_devices_gt_3.sbd_devices_input
        with self.assertRaises(ValueError) as err:
            self.sbd_inst_devices_gt_3._verify_sbd_device(dev_list)
        self.assertEqual("Maximum number of SBD device is 3", str(err.exception))

    @mock.patch('crmsh.bootstrap.SBDManager._compare_device_uuid')
    @mock.patch('crmsh.bootstrap.is_block_device')
    def test_verify_sbd_device_not_block(self, mock_block_device, mock_compare):
        assert self.sbd_inst.sbd_devices_input == ["/dev/sdb1", "/dev/sdc1"]
        dev_list = self.sbd_inst.sbd_devices_input
        mock_block_device.side_effect = [True, False]

        with self.assertRaises(ValueError) as err:
            self.sbd_inst._verify_sbd_device(dev_list)
        self.assertEqual("/dev/sdc1 doesn't look like a block device", str(err.exception))

        mock_block_device.assert_has_calls([mock.call("/dev/sdb1"), mock.call("/dev/sdc1")])
        mock_compare.assert_called_once_with("/dev/sdb1", [])

    @mock.patch('crmsh.bootstrap.SBDManager._verify_sbd_device')
    @mock.patch('crmsh.bootstrap.SBDManager._parse_sbd_device')
    def test_get_sbd_device_from_option(self, mock_parse, mock_verify):
        mock_parse.return_value = ["/dev/sdb1", "/dev/sdc1"]
        self.sbd_inst._get_sbd_device()
        mock_parse.assert_called_once_with()
        mock_verify.assert_called_once_with(mock_parse.return_value)

    @mock.patch('crmsh.bootstrap.SBDManager._get_sbd_device_interactive')
    def test_get_sbd_device_from_interactive(self, mock_interactive):
        mock_interactive.return_value = ["/dev/sdb1", "/dev/sdc1"]
        self.sbd_inst_interactive._get_sbd_device()
        mock_interactive.assert_called_once_with()

    def test_get_sbd_device_diskless(self):
        self.sbd_inst_diskless._get_sbd_device()

    @mock.patch('crmsh.bootstrap.error')
    @mock.patch('crmsh.bootstrap.invoke')
    def test_initialize_sbd(self, mock_invoke, mock_error):
        self.sbd_inst._sbd_devices = ["/dev/sdb1", "/dev/sdc1"]
        mock_invoke.side_effect = [(True, None, None), (False, None, "error")]
        mock_error.side_effect = ValueError

        with self.assertRaises(ValueError):
            self.sbd_inst._initialize_sbd()

        mock_invoke.assert_has_calls([
            mock.call("sbd -d /dev/sdb1 create"),
            mock.call("sbd -d /dev/sdc1 create")
            ])
        mock_error.assert_called_once_with("Failed to initialize SBD device /dev/sdc1: error")

    @mock.patch('crmsh.bootstrap.csync2_update')
    @mock.patch('crmsh.utils.sysconfig_set')
    @mock.patch('shutil.copyfile')
    def test_update_configuration(self, mock_copy, mock_sysconfig, mock_update):
        self.sbd_inst._sbd_devices = ["/dev/sdb1", "/dev/sdc1"]
        self.sbd_inst._watchdog_inst = mock.Mock(watchdog_device_name="/dev/watchdog")

        self.sbd_inst._update_configuration()

        mock_copy.assert_called_once_with("/usr/share/fillup-templates/sysconfig.sbd", "/etc/sysconfig/sbd")
        mock_sysconfig.assert_called_once_with("/etc/sysconfig/sbd", SBD_PACEMAKER='yes', SBD_STARTMODE='always', SBD_DELAY_START='no', SBD_WATCHDOG_DEV='/dev/watchdog', SBD_DEVICE='/dev/sdb1;/dev/sdc1')
        mock_update.assert_called_once_with("/etc/sysconfig/sbd")

    @mock.patch('crmsh.bootstrap.utils.parse_sysconfig')
    def test_get_sbd_device_from_config_none(self, mock_parse):
        mock_parse_inst = mock.Mock()
        mock_parse.return_value = mock_parse_inst
        mock_parse_inst.get.return_value = None

        res = self.sbd_inst._get_sbd_device_from_config()
        assert res is None

        mock_parse.assert_called_once_with("/etc/sysconfig/sbd")
        mock_parse_inst.get.assert_called_once_with("SBD_DEVICE")

    @mock.patch('crmsh.bootstrap.utils.parse_sysconfig')
    def test_get_sbd_device_from_config(self, mock_parse):
        mock_parse_inst = mock.Mock()
        mock_parse.return_value = mock_parse_inst
        mock_parse_inst.get.return_value = "/dev/sdb1;/dev/sdc1"

        res = self.sbd_inst._get_sbd_device_from_config()
        assert res == ["/dev/sdb1", "/dev/sdc1"]

        mock_parse.assert_called_once_with("/etc/sysconfig/sbd")
        mock_parse_inst.get.assert_called_once_with("SBD_DEVICE")

    @mock.patch('crmsh.utils.package_is_installed')
    def test_sbd_init_not_installed(self, mock_package):
        mock_package.return_value = False
        self.sbd_inst.sbd_init()
        mock_package.assert_called_once_with("sbd")

    @mock.patch('crmsh.bootstrap.invoke')
    @mock.patch('crmsh.bootstrap.status_done')
    @mock.patch('crmsh.bootstrap.SBDManager._update_configuration')
    @mock.patch('crmsh.bootstrap.SBDManager._initialize_sbd')
    @mock.patch('crmsh.bootstrap.status_long')
    @mock.patch('crmsh.bootstrap.SBDManager._get_sbd_device')
    @mock.patch('crmsh.bootstrap.Watchdog')
    @mock.patch('crmsh.utils.package_is_installed')
    def test_sbd_init_return(self, mock_package, mock_watchdog, mock_get_device, mock_status, mock_initialize, mock_update, mock_status_done, mock_invoke):
        mock_package.return_value = True
        self.sbd_inst._sbd_devices = None
        self.sbd_inst.diskless_sbd = False
        mock_watchdog_inst = mock.Mock()
        mock_watchdog.return_value = mock_watchdog_inst
        mock_watchdog_inst.init_watchdog = mock.Mock()

        self.sbd_inst.sbd_init()

        mock_package.assert_called_once_with("sbd")
        mock_get_device.assert_called_once_with()
        mock_status.assert_not_called()
        mock_initialize.assert_not_called()
        mock_update.assert_not_called()
        mock_status_done.assert_not_called()
        mock_watchdog.assert_called_once_with(_input=None)
        mock_watchdog_inst.init_watchdog.assert_called_once_with()
        mock_invoke.assert_called_once_with("systemctl disable sbd.service")

    @mock.patch('crmsh.bootstrap.status_done')
    @mock.patch('crmsh.bootstrap.SBDManager._update_configuration')
    @mock.patch('crmsh.bootstrap.SBDManager._initialize_sbd')
    @mock.patch('crmsh.bootstrap.status_long')
    @mock.patch('crmsh.bootstrap.SBDManager._get_sbd_device')
    @mock.patch('crmsh.bootstrap.Watchdog')
    @mock.patch('crmsh.utils.package_is_installed')
    def test_sbd_init(self, mock_package, mock_watchdog, mock_get_device, mock_status, mock_initialize, mock_update, mock_status_done):
        bootstrap._context = mock.Mock(watchdog=None)
        mock_package.return_value = True
        mock_watchdog_inst = mock.Mock()
        mock_watchdog.return_value = mock_watchdog_inst
        mock_watchdog_inst.init_watchdog = mock.Mock()
        self.sbd_inst_diskless.sbd_init()

        mock_package.assert_called_once_with("sbd")
        mock_get_device.assert_called_once_with()
        mock_status.assert_called_once_with("Initializing diskless SBD...")
        mock_initialize.assert_called_once_with()
        mock_update.assert_called_once_with()
        mock_status_done.assert_called_once_with()
        mock_watchdog.assert_called_once_with(_input=None)
        mock_watchdog_inst.init_watchdog.assert_called_once_with()

    @mock.patch('crmsh.utils.package_is_installed')
    def test_configure_sbd_resource_not_installed(self, mock_package):
        mock_package.return_value = False
        self.sbd_inst.configure_sbd_resource()
        mock_package.assert_called_once_with("sbd")

    @mock.patch('crmsh.bootstrap.error')
    @mock.patch('crmsh.bootstrap.invokerc')
    @mock.patch('crmsh.bootstrap.SBDManager._get_sbd_device_from_config')
    @mock.patch('crmsh.utils.service_is_enabled')
    @mock.patch('crmsh.utils.package_is_installed')
    def test_configure_sbd_resource_error_primitive(self, mock_package, mock_enabled, mock_get_device, mock_invoke, mock_error):
        mock_package.return_value = True
        mock_enabled.return_value = True
        mock_get_device.return_value = ["/dev/sdb1"]
        mock_invoke.return_value = False
        mock_error.side_effect = ValueError

        with self.assertRaises(ValueError):
            self.sbd_inst.configure_sbd_resource()

        mock_package.assert_called_once_with("sbd")
        mock_enabled.assert_called_once_with("sbd.service")
        mock_get_device.assert_called_once_with()
        mock_invoke.assert_called_once_with("crm configure primitive stonith-sbd stonith:external/sbd pcmk_delay_max=30s")
        mock_error.assert_called_once_with("Can't create stonith-sbd primitive")

    @mock.patch('crmsh.bootstrap.error')
    @mock.patch('crmsh.bootstrap.invokerc')
    @mock.patch('crmsh.bootstrap.SBDManager._get_sbd_device_from_config')
    @mock.patch('crmsh.utils.service_is_enabled')
    @mock.patch('crmsh.utils.package_is_installed')
    def test_configure_sbd_resource_error_property(self, mock_package, mock_enabled, mock_get_device, mock_invoke, mock_error):
        mock_package.return_value = True
        mock_enabled.return_value = True
        mock_get_device.return_value = ["/dev/sdb1"]
        mock_invoke.side_effect = [True, False]
        mock_error.side_effect = ValueError

        with self.assertRaises(ValueError):
            self.sbd_inst.configure_sbd_resource()

        mock_package.assert_called_once_with("sbd")
        mock_enabled.assert_called_once_with("sbd.service")
        mock_get_device.assert_called_once_with()
        mock_invoke.assert_has_calls([
            mock.call("crm configure primitive stonith-sbd stonith:external/sbd pcmk_delay_max=30s"),
            mock.call("crm configure property stonith-enabled=true")
            ])
        mock_error.assert_called_once_with("Can't enable STONITH for SBD")

    @mock.patch('crmsh.bootstrap.error')
    @mock.patch('crmsh.bootstrap.invokerc')
    @mock.patch('crmsh.bootstrap.SBDManager._get_sbd_device_from_config')
    @mock.patch('crmsh.utils.service_is_enabled')
    @mock.patch('crmsh.utils.package_is_installed')
    def test_configure_sbd_resource_diskless(self, mock_package, mock_enabled, mock_get_device, mock_invoke, mock_error):
        mock_package.return_value = True
        mock_enabled.return_value = True
        mock_get_device.return_value = None
        mock_invoke.return_value = False
        mock_error.side_effect = ValueError

        with self.assertRaises(ValueError):
            self.sbd_inst_diskless.configure_sbd_resource()

        mock_package.assert_called_once_with("sbd")
        mock_enabled.assert_called_once_with("sbd.service")
        mock_get_device.assert_called_once_with()
        mock_invoke.assert_called_once_with("crm configure property stonith-enabled=true stonith-watchdog-timeout=5s")
        mock_error.assert_called_once_with("Can't enable STONITH for diskless SBD")

    @mock.patch('crmsh.utils.package_is_installed')
    def test_join_sbd_config_not_installed(self, mock_package):
        mock_package.return_value = False
        self.sbd_inst.join_sbd("node1")
        mock_package.assert_called_once_with("sbd")

    @mock.patch('crmsh.bootstrap.invoke')
    @mock.patch('os.path.exists')
    @mock.patch('crmsh.utils.package_is_installed')
    def test_join_sbd_config_not_exist(self, mock_package, mock_exists, mock_invoke):
        mock_package.return_value = True
        mock_exists.return_value = False
        self.sbd_inst.join_sbd("node1")
        mock_package.assert_called_once_with("sbd")
        mock_exists.assert_called_once_with("/etc/sysconfig/sbd")
        mock_invoke.assert_called_once_with("systemctl disable sbd.service")

    @mock.patch('crmsh.bootstrap.invoke')
    @mock.patch('crmsh.utils.service_is_enabled')
    @mock.patch('os.path.exists')
    @mock.patch('crmsh.utils.package_is_installed')
    def test_join_sbd_config_disabled(self, mock_package, mock_exists, mock_enabled, mock_invoke):
        mock_package.return_value = True
        mock_exists.return_value = True
        mock_enabled.return_value = False

        self.sbd_inst.join_sbd("node1")

        mock_package.assert_called_once_with("sbd")
        mock_exists.assert_called_once_with("/etc/sysconfig/sbd")
        mock_invoke.assert_called_once_with("systemctl disable sbd.service")
        mock_enabled.assert_called_once_with("sbd.service", "node1")

    @mock.patch('crmsh.bootstrap.status')
    @mock.patch('crmsh.bootstrap.SBDManager._verify_sbd_device')
    @mock.patch('crmsh.bootstrap.SBDManager._get_sbd_device_from_config')
    @mock.patch('crmsh.bootstrap.Watchdog')
    @mock.patch('crmsh.bootstrap.invoke')
    @mock.patch('crmsh.utils.service_is_enabled')
    @mock.patch('os.path.exists')
    @mock.patch('crmsh.utils.package_is_installed')
    def test_join_sbd(self, mock_package, mock_exists, mock_enabled, mock_invoke, mock_watchdog, mock_get_device, mock_verify, mock_status):
        mock_package.return_value = True
        mock_exists.return_value = True
        mock_enabled.return_value = True
        mock_get_device.return_value = ["/dev/sdb1"]
        mock_watchdog_inst = mock.Mock()
        mock_watchdog.return_value = mock_watchdog_inst
        mock_watchdog_inst.join_watchdog = mock.Mock()

        self.sbd_inst.join_sbd("node1")

        mock_package.assert_called_once_with("sbd")
        mock_exists.assert_called_once_with("/etc/sysconfig/sbd")
        mock_invoke.assert_called_once_with("systemctl enable sbd.service")
        mock_get_device.assert_called_once_with()
        mock_verify.assert_called_once_with(["/dev/sdb1"], ["node1"])
        mock_enabled.assert_called_once_with("sbd.service", "node1")
        mock_status.assert_called_once_with("Got SBD configuration")
        mock_watchdog.assert_called_once_with(peer_host="node1")
        mock_watchdog_inst.join_watchdog.assert_called_once_with()

    @mock.patch('crmsh.bootstrap.SBDManager._get_sbd_device_from_config')
    def test_verify_sbd_device_classmethod_exception(self, mock_get_config):
        mock_get_config.return_value = []
        with self.assertRaises(ValueError) as err:
            bootstrap.SBDManager.verify_sbd_device()
        self.assertEqual("No sbd device configured", str(err.exception))
        mock_get_config.assert_called_once_with()

    @mock.patch('crmsh.bootstrap.SBDManager._verify_sbd_device')
    @mock.patch('crmsh.utils.list_cluster_nodes_except_me')
    @mock.patch('crmsh.bootstrap.SBDManager._get_sbd_device_from_config')
    def test_verify_sbd_device_classmethod(self, mock_get_config, mock_list_nodes, mock_verify):
        mock_get_config.return_value = ["/dev/sda1"]
        mock_list_nodes.return_value = ["node1"]
        bootstrap.SBDManager.verify_sbd_device()
        mock_get_config.assert_called_once_with()
        mock_verify.assert_called_once_with(["/dev/sda1"], ["node1"])

    @mock.patch('crmsh.bootstrap.SBDManager._get_device_uuid')
    def test_compare_device_uuid_return(self, mock_get_uuid):
        self.sbd_inst._compare_device_uuid("/dev/sdb1", None)
        mock_get_uuid.assert_not_called()

    @mock.patch('crmsh.bootstrap.SBDManager._get_device_uuid')
    def test_compare_device_uuid(self, mock_get_uuid):
        mock_get_uuid.side_effect = ["1234", "5678"]
        with self.assertRaises(ValueError) as err:
            self.sbd_inst._compare_device_uuid("/dev/sdb1", ["node1"])
        self.assertEqual("Device /dev/sdb1 doesn't have the same UUID with node1", str(err.exception))
        mock_get_uuid.assert_has_calls([mock.call("/dev/sdb1"), mock.call("/dev/sdb1", "node1")])

    @mock.patch('crmsh.utils.get_stdout_stderr')
    def test_get_device_uuid_error_dump(self, mock_run):
        mock_run.return_value = (1, None, "error data")
        with self.assertRaises(ValueError) as err:
            self.sbd_inst._get_device_uuid("/dev/sdb1")
        self.assertEqual("Cannot dump sbd meta-data: error data", str(err.exception))
        mock_run.assert_called_once_with("sbd -d /dev/sdb1 dump")

    @mock.patch('crmsh.utils.get_stdout_stderr')
    def test_get_device_uuid_not_match(self, mock_run):
        mock_run.return_value = (0, "output data", None)
        with self.assertRaises(ValueError) as err:
            self.sbd_inst._get_device_uuid("/dev/sdb1")
        self.assertEqual("Cannot find sbd device UUID for /dev/sdb1", str(err.exception))
        mock_run.assert_called_once_with("sbd -d /dev/sdb1 dump")

    @mock.patch('crmsh.utils.get_stdout_stderr')
    def test_get_device_uuid(self, mock_run):
        output = """
        ==Dumping header on disk /dev/sda1
        Header version     : 2.1
        UUID               : a2e9a92c-cc72-4ef9-ac55-ccc342f3546b
        Number of slots    : 255
        Sector size        : 512
        Timeout (watchdog) : 5
        Timeout (allocate) : 2
        Timeout (loop)     : 1
        Timeout (msgwait)  : 10
        ==Header on disk /dev/sda1 is dumped
        """
        mock_run.return_value = (0, output, None)
        res = self.sbd_inst._get_device_uuid("/dev/sda1")
        self.assertEqual(res, "a2e9a92c-cc72-4ef9-ac55-ccc342f3546b")
        mock_run.assert_called_once_with("sbd -d /dev/sda1 dump")


class TestBootstrap(unittest.TestCase):
    """
    Unitary tests for crmsh/bootstrap.py
    """

    @classmethod
    def setUpClass(cls):
        """
        Global setUp.
        """

    def setUp(self):
        """
        Test setUp.
        """
        self.qdevice_with_ip = corosync.QDevice("10.10.10.123")

    def tearDown(self):
        """
        Test tearDown.
        """

    @classmethod
    def tearDownClass(cls):
        """
        Global tearDown.
        """

    @mock.patch('crmsh.bootstrap.configure_local_ssh_key')
    @mock.patch('crmsh.utils.start_service')
    def test_init_ssh(self, mock_start_service, mock_config_ssh):
        bootstrap.init_ssh()
        mock_start_service.assert_called_once_with("sshd.service", enable=True)
        mock_config_ssh.assert_called_once_with()

    @mock.patch('crmsh.bootstrap.append_unique')
    @mock.patch('builtins.open', create=True)
    @mock.patch('crmsh.utils.this_node')
    @mock.patch('crmsh.bootstrap.invoke')
    @mock.patch('crmsh.bootstrap.status')
    @mock.patch('os.path.exists')
    def test_configure_local_ssh_key(self, mock_exists, mock_status, mock_invoke,
            mock_this_node, mock_open_file, mock_append):
        mock_exists.side_effect = [False, False]
        mock_this_node.return_value = "node1"

        bootstrap.configure_local_ssh_key()

        mock_exists.assert_has_calls([
            mock.call(bootstrap.RSA_PRIVATE_KEY),
            mock.call(bootstrap.AUTHORIZED_KEYS_FILE)
            ])
        mock_status.assert_called_once_with("Generating SSH key")
        mock_invoke.assert_called_once_with("ssh-keygen -q -f {} -C 'Cluster Internal on {}' -N ''".format(bootstrap.RSA_PRIVATE_KEY, mock_this_node.return_value))
        mock_this_node.assert_called_once_with()
        mock_open_file.assert_called_once_with(bootstrap.AUTHORIZED_KEYS_FILE, 'w')
        mock_append.assert_called_once_with(bootstrap.RSA_PUBLIC_KEY, bootstrap.AUTHORIZED_KEYS_FILE)

    @mock.patch('crmsh.bootstrap.append')
    @mock.patch('crmsh.utils.check_file_content_included')
    def test_append_unique(self, mock_check, mock_append):
        mock_check.return_value = False
        bootstrap.append_unique("fromfile", "tofile")
        mock_check.assert_called_once_with("fromfile", "tofile")
        mock_append.assert_called_once_with("fromfile", "tofile")

    @mock.patch('crmsh.bootstrap.error')
    @mock.patch('crmsh.bootstrap.invoke')
    def test_append_to_remote_file(self, mock_invoke, mock_error):
        mock_invoke.return_value = (False, None, "error")
        error_string = 'Failed to append contents of fromfile to node1:\n"error"\n\n    crmsh has no way to help you to setup up passwordless ssh among nodes at this time. \n    As the hint, likely, `PasswordAuthentication` is \'no\' in /etc/ssh/sshd_config. \n    Given in this case, users must setup passwordless ssh beforehand, or change it to \'yes\' and manage passwords properly\n    '
        bootstrap.append_to_remote_file("fromfile", "node1", "tofile")
        cmd = "cat fromfile | ssh -oStrictHostKeyChecking=no root@node1 'cat >> tofile'"
        mock_invoke.assert_called_once_with(cmd)
        mock_error.assert_called_once_with(error_string)

    @mock.patch('crmsh.bootstrap.invokerc')
    def test_fetch_public_key_from_remote_node_exception(self, mock_invoke):
        mock_invoke.side_effect = [False, False, False, False]

        with self.assertRaises(ValueError) as err:
            bootstrap.fetch_public_key_from_remote_node("node1")
        self.assertEqual("No ssh key exist on node1", str(err.exception))

        mock_invoke.assert_has_calls([
            mock.call("ssh -oStrictHostKeyChecking=no root@node1 'test -f /root/.ssh/id_rsa.pub'"),
            mock.call("ssh -oStrictHostKeyChecking=no root@node1 'test -f /root/.ssh/id_ecdsa.pub'"),
            mock.call("ssh -oStrictHostKeyChecking=no root@node1 'test -f /root/.ssh/id_ed25519.pub'"),
            mock.call("ssh -oStrictHostKeyChecking=no root@node1 'test -f /root/.ssh/id_dsa.pub'")
            ])

    @mock.patch('crmsh.tmpfiles.create')
    @mock.patch('crmsh.bootstrap.invokerc')
    @mock.patch('crmsh.bootstrap.invoke')
    def test_fetch_public_key_from_remote_node(self, mock_invoke, mock_invokerc, mock_tmpfile):
        mock_invokerc.return_value = True
        mock_invoke.return_value = (True, None, None)
        mock_tmpfile.return_value = (0, "temp_file_name")

        res = bootstrap.fetch_public_key_from_remote_node("node1")
        self.assertEqual(res, "temp_file_name")

        mock_invokerc.assert_called_once_with("ssh -oStrictHostKeyChecking=no root@node1 'test -f /root/.ssh/id_rsa.pub'")
        mock_invoke.assert_called_once_with("scp -oStrictHostKeyChecking=no root@node1:/root/.ssh/id_rsa.pub temp_file_name")
        mock_tmpfile.assert_called_once_with()

    @mock.patch('crmsh.bootstrap.error')
    def test_join_ssh_no_seed_host(self, mock_error):
        mock_error.side_effect = ValueError
        with self.assertRaises(ValueError):
            bootstrap.join_ssh(None)
        mock_error.assert_called_once_with("No existing IP/hostname specified (use -c option)")

    @mock.patch('crmsh.bootstrap.error')
    @mock.patch('crmsh.bootstrap.invoke')
    @mock.patch('crmsh.bootstrap.swap_public_ssh_key')
    @mock.patch('crmsh.bootstrap.configure_local_ssh_key')
    @mock.patch('crmsh.utils.start_service')
    def test_join_ssh(self, mock_start_service, mock_config_ssh, mock_swap, mock_invoke, mock_error):
        bootstrap._context = mock.Mock(default_nic_list=["eth1"])
        mock_invoke.return_value = (False, None, "error")

        bootstrap.join_ssh("node1")

        mock_start_service.assert_called_once_with("sshd.service", enable=True)
        mock_config_ssh.assert_called_once_with()
        mock_swap.assert_called_once_with("node1")
        mock_invoke.assert_called_once_with("ssh root@node1 crm cluster init -i eth1 ssh_remote")
        mock_error.assert_called_once_with("Can't invoke crm cluster init -i eth1 ssh_remote on node1: error")

    @mock.patch('crmsh.bootstrap.warn')
    @mock.patch('crmsh.bootstrap.fetch_public_key_from_remote_node')
    @mock.patch('crmsh.utils.check_ssh_passwd_need')
    def test_swap_public_ssh_key_exception(self, mock_check_passwd, mock_fetch, mock_warn):
        mock_check_passwd.return_value = False
        mock_fetch.side_effect = ValueError("No key exist")

        bootstrap.swap_public_ssh_key("node1")

        mock_warn.assert_called_once_with(mock_fetch.side_effect)
        mock_check_passwd.assert_called_once_with("node1")
        mock_fetch.assert_called_once_with("node1")

    @mock.patch('crmsh.bootstrap.append_unique')
    @mock.patch('crmsh.bootstrap.fetch_public_key_from_remote_node')
    @mock.patch('crmsh.bootstrap.append_to_remote_file')
    @mock.patch('crmsh.bootstrap.status')
    @mock.patch('crmsh.utils.check_ssh_passwd_need')
    def test_swap_public_ssh_key(self, mock_check_passwd, mock_status, mock_append_remote, mock_fetch, mock_append_unique):
        mock_check_passwd.return_value = True
        mock_fetch.return_value = "file1"

        bootstrap.swap_public_ssh_key("node1")

        mock_check_passwd.assert_called_once_with("node1")
        mock_status.assert_called_once_with("Configuring SSH passwordless with root@node1")
        mock_append_remote.assert_called_once_with(bootstrap.RSA_PUBLIC_KEY, "node1", bootstrap.AUTHORIZED_KEYS_FILE)
        mock_fetch.assert_called_once_with("node1")
        mock_append_unique.assert_called_once_with("file1", bootstrap.AUTHORIZED_KEYS_FILE)

    @mock.patch('crmsh.bootstrap.error')
    @mock.patch('crmsh.utils.get_stdout_stderr')
    def test_setup_passwordless_with_other_nodes_failed_fetch_nodelist(self, mock_run, mock_error):
        mock_run.return_value = (1, None, None)
        mock_error.side_effect = SystemExit

        with self.assertRaises(SystemExit):
            bootstrap.setup_passwordless_with_other_nodes("node1")

        mock_run.assert_called_once_with("ssh -o StrictHostKeyChecking=no root@node1 crm_node -l")
        mock_error.assert_called_once_with("Can't fetch cluster nodes list from node1: None")

    @mock.patch('crmsh.bootstrap.error')
    @mock.patch('crmsh.utils.get_stdout_stderr')
    def test_setup_passwordless_with_other_nodes_failed_fetch_hostname(self, mock_run, mock_error):
        out_node_list = """1 node1 member
        2 node2 member"""
        mock_run.side_effect = [
                (0, out_node_list, None),
                (1, None, None)
                ]
        mock_error.side_effect = SystemExit

        with self.assertRaises(SystemExit):
            bootstrap.setup_passwordless_with_other_nodes("node1")

        mock_run.assert_has_calls([
            mock.call("ssh -o StrictHostKeyChecking=no root@node1 crm_node -l"),
            mock.call("ssh -o StrictHostKeyChecking=no root@node1 hostname")
            ])
        mock_error.assert_called_once_with("Can't fetch hostname of node1: None")

    @mock.patch('crmsh.bootstrap.swap_public_ssh_key')
    @mock.patch('crmsh.utils.get_stdout_stderr')
    def test_setup_passwordless_with_other_nodes(self, mock_run, mock_swap):
        out_node_list = """1 node1 member
        2 node2 member"""
        mock_run.side_effect = [
                (0, out_node_list, None),
                (0, "node1", None)
                ]

        bootstrap.setup_passwordless_with_other_nodes("node1")

        mock_run.assert_has_calls([
            mock.call("ssh -o StrictHostKeyChecking=no root@node1 crm_node -l"),
            mock.call("ssh -o StrictHostKeyChecking=no root@node1 hostname")
            ])
        mock_swap.assert_called_once_with("node2")

    @mock.patch('builtins.open')
    @mock.patch('crmsh.bootstrap.append')
    @mock.patch('os.path.join')
    @mock.patch('os.path.exists')
    def test_init_ssh_remote_no_sshkey(self, mock_exists, mock_join, mock_append, mock_open_file):
        mock_exists.side_effect = [False, True, False, False, False]
        mock_join.side_effect = ["/root/.ssh/id_rsa",
                                 "/root/.ssh/id_dsa",
                                 "/root/.ssh/id_ecdsa",
                                 "/root/.ssh/id_ed25519"]
        mock_open_file.side_effect = [
            mock.mock_open().return_value,
            mock.mock_open(read_data="data1 data2").return_value,
            mock.mock_open(read_data="data1111").return_value
        ]

        bootstrap.init_ssh_remote()

        mock_open_file.assert_has_calls([
            mock.call("/root/.ssh/authorized_keys", 'w'),
            mock.call("/root/.ssh/authorized_keys", "r+"),
            mock.call("/root/.ssh/id_rsa.pub")
        ])
        mock_exists.assert_has_calls([
            mock.call("/root/.ssh/authorized_keys"),
            mock.call("/root/.ssh/id_rsa"),
            mock.call("/root/.ssh/id_dsa"),
            mock.call("/root/.ssh/id_ecdsa"),
            mock.call("/root/.ssh/id_ed25519"),
        ])
        mock_append.assert_called_once_with("/root/.ssh/id_rsa.pub", "/root/.ssh/authorized_keys")

    @mock.patch('crmsh.utils.IP.is_valid_ip')
    @mock.patch('crmsh.utils.get_stdout_stderr')
    def test_get_cluster_node_hostname_None(self, mock_stdout_stderr, mock_valid_ip):
        bootstrap._context = mock.Mock(cluster_node=None)

        peer_node = bootstrap.get_cluster_node_hostname()
        assert peer_node is None

        mock_valid_ip.assert_not_called()
        mock_stdout_stderr.assert_not_called()

    @mock.patch('crmsh.utils.IP.is_valid_ip')
    @mock.patch('crmsh.utils.get_stdout_stderr')
    def test_get_cluster_node_hostname_IP(self, mock_stdout_stderr, mock_valid_ip):
        bootstrap._context = mock.Mock(cluster_node="1.1.1.1")
        mock_valid_ip.return_value = True
        mock_stdout_stderr.return_value = (0, "node1", None)

        peer_node = bootstrap.get_cluster_node_hostname()
        assert peer_node == "node1"

        mock_valid_ip.assert_called_once_with("1.1.1.1")
        mock_stdout_stderr.assert_called_once_with("ssh 1.1.1.1 crm_node --name")

    @mock.patch('crmsh.utils.IP.is_valid_ip')
    @mock.patch('crmsh.utils.get_stdout_stderr')
    def test_get_cluster_node_hostname_HOST(self, mock_stdout_stderr, mock_valid_ip):
        bootstrap._context = mock.Mock(cluster_node="node2")
        mock_valid_ip.return_value = False

        peer_node = bootstrap.get_cluster_node_hostname()
        assert peer_node == "node2"

        mock_valid_ip.assert_called_once_with("node2")
        mock_stdout_stderr.assert_not_called()

    @mock.patch('crmsh.utils.this_node')
    @mock.patch('re.search')
    @mock.patch('crmsh.bootstrap.get_cluster_node_hostname')
    def test_is_online_local_offline(self, mock_get_peer, mock_search, mock_this_node):
        mock_this_node.return_value = "node1"
        mock_search.return_value = None

        assert bootstrap.is_online("text") is False

        mock_this_node.assert_called_once_with()
        mock_get_peer.assert_not_called()
        mock_search.assert_called_once_with("Online: .* node1 ", "text")

    @mock.patch('crmsh.utils.this_node')
    @mock.patch('re.search')
    @mock.patch('crmsh.bootstrap.get_cluster_node_hostname')
    def test_is_online_on_init_node(self, mock_get_peer, mock_search, mock_this_node):
        mock_search.return_value = mock.Mock()
        mock_this_node.return_value = "node1"
        mock_get_peer.return_value = None

        assert bootstrap.is_online("text") is True

        mock_this_node.assert_called_once_with()
        mock_get_peer.assert_called_once_with()
        mock_search.assert_called_once_with("Online: .* node1 ", "text")

    @mock.patch('crmsh.bootstrap.error')
    @mock.patch('crmsh.utils.stop_service')
    @mock.patch('crmsh.bootstrap.csync2_update')
    @mock.patch('crmsh.corosync.conf')
    @mock.patch('shutil.copy')
    @mock.patch('crmsh.utils.this_node')
    @mock.patch('re.search')
    @mock.patch('crmsh.bootstrap.get_cluster_node_hostname')
    def test_is_online_peer_offline(self, mock_get_peer, mock_search, mock_this_node,
            mock_copy, mock_corosync_conf, mock_csync2, mock_stop_service, mock_error):
        bootstrap.COROSYNC_CONF_ORIG = "/tmp/crmsh_tmpfile"
        mock_search.side_effect = [ mock.Mock(), None ]
        mock_this_node.return_value = "node2"
        mock_get_peer.return_value = "node1"
        mock_corosync_conf.side_effect = [ "/etc/corosync/corosync.conf", 
                "/etc/corosync/corosync.conf"]

        bootstrap.is_online("text")

        mock_this_node.assert_called_once_with()
        mock_get_peer.assert_called_once_with()
        mock_search.assert_has_calls([
            mock.call("Online: .* node2 ", "text"),
            mock.call("Online: .* node1 ", "text")
            ])
        mock_corosync_conf.assert_has_calls([
            mock.call(),
            mock.call()
            ])
        mock_copy.assert_called_once_with(bootstrap.COROSYNC_CONF_ORIG, "/etc/corosync/corosync.conf")
        mock_csync2.assert_called_once_with("/etc/corosync/corosync.conf")
        mock_stop_service.assert_called_once_with("corosync")
        mock_error.assert_called_once_with("Cannot see peer node \"node1\", please check the communication IP")

    @mock.patch('crmsh.bootstrap.error')
    @mock.patch('crmsh.utils.stop_service')
    @mock.patch('crmsh.bootstrap.csync2_update')
    @mock.patch('crmsh.corosync.conf')
    @mock.patch('shutil.copy')
    @mock.patch('crmsh.utils.this_node')
    @mock.patch('re.search')
    @mock.patch('crmsh.bootstrap.get_cluster_node_hostname')
    def test_is_online_both_online(self, mock_get_peer, mock_search, mock_this_node,
            mock_copy, mock_corosync_conf, mock_csync2, mock_stop_service, mock_error):
        mock_search.side_effect = [ mock.Mock(), mock.Mock() ]
        mock_this_node.return_value = "node2"
        mock_get_peer.return_value = "node1"

        assert bootstrap.is_online("text") is True

        mock_this_node.assert_called_once_with()
        mock_get_peer.assert_called_once_with()
        mock_search.assert_has_calls([
            mock.call("Online: .* node2 ", "text"),
            mock.call("Online: .* node1 ", "text")
            ])
        mock_corosync_conf.assert_not_called()
        mock_copy.assert_not_called()
        mock_csync2.assert_not_called()
        mock_stop_service.assert_not_called()
        mock_error.assert_not_called()

    @mock.patch('crmsh.bootstrap.invokerc')
    @mock.patch('crmsh.bootstrap.invoke')
    def test_csync2_update_no_conflicts(self, mock_invoke, mock_invokerc):
        mock_invokerc.return_value = True
        bootstrap.csync2_update("/etc/corosync.conf")
        mock_invoke.assert_called_once_with("csync2 -rm /etc/corosync.conf")
        mock_invokerc.assert_called_once_with("csync2 -rxv /etc/corosync.conf")

    @mock.patch('crmsh.bootstrap.warn')
    @mock.patch('crmsh.bootstrap.invokerc')
    @mock.patch('crmsh.bootstrap.invoke')
    def test_csync2_update(self, mock_invoke, mock_invokerc, mock_warn):
        mock_invokerc.side_effect = [False, False]
        bootstrap.csync2_update("/etc/corosync.conf")
        mock_invoke.assert_has_calls([
            mock.call("csync2 -rm /etc/corosync.conf"),
            mock.call("csync2 -rf /etc/corosync.conf")
            ])
        mock_invokerc.assert_has_calls([
            mock.call("csync2 -rxv /etc/corosync.conf"),
            mock.call("csync2 -rxv /etc/corosync.conf")
            ])
        mock_warn.assert_called_once_with("/etc/corosync.conf was not synced")

    @mock.patch('crmsh.utils.InterfacesInfo')
    def test_init_network(self, mock_interfaces):
        mock_interfaces_inst = mock.Mock()
        mock_interfaces.return_value = mock_interfaces_inst
        mock_interfaces_inst.get_default_nic_list_from_route.return_value = ["eth0", "eth1"]
        bootstrap._context = mock.Mock(ipv6=False, second_heartbeat=False, nic_list=["eth0", "eth1"], default_nic_list=["eth0", "eth1"])

        bootstrap.init_network()

        mock_interfaces.assert_called_once_with(False, False, bootstrap._context.nic_list)
        mock_interfaces_inst.get_interfaces_info.assert_called_once_with()
        mock_interfaces_inst.get_default_nic_list_from_route.assert_called_once_with()
        mock_interfaces_inst.get_default_ip_list.assert_called_once_with()

    @mock.patch('crmsh.utils.disable_service')
    @mock.patch('crmsh.bootstrap.status')
    def test_init_qdevice_no_config(self, mock_status, mock_disable):
        bootstrap._context = mock.Mock(qdevice_inst=None)
        bootstrap.init_qdevice()
        mock_status.assert_not_called()
        mock_disable.assert_called_once_with("corosync-qdevice.service")

    @mock.patch('crmsh.bootstrap.error')
    @mock.patch('crmsh.bootstrap.invoke')
    @mock.patch('crmsh.utils.check_ssh_passwd_need')
    @mock.patch('crmsh.bootstrap.status')
    def test_init_qdevice_copy_ssh_key_failed(self, mock_status, mock_ssh, mock_invoke, mock_error):
        bootstrap._context = mock.Mock(qdevice_inst=self.qdevice_with_ip)
        mock_ssh.return_value = True
        mock_invoke.return_value = (False, None, "error")
        mock_error.side_effect = SystemExit

        with self.assertRaises(SystemExit):
            bootstrap.init_qdevice()

        mock_status.assert_has_calls([
            mock.call("\nConfigure Qdevice/Qnetd:"),
            mock.call("Copy ssh key to qnetd node(10.10.10.123)")
            ])
        mock_ssh.assert_called_once_with("10.10.10.123")
        mock_invoke.assert_called_once_with("ssh-copy-id -i /root/.ssh/id_rsa.pub root@10.10.10.123")
        mock_error.assert_called_once_with("Failed to copy ssh key: error")

    @mock.patch('crmsh.bootstrap.start_qdevice_service')
    @mock.patch('crmsh.bootstrap.confirm')
    @mock.patch('crmsh.utils.is_qdevice_configured')
    @mock.patch('crmsh.utils.check_ssh_passwd_need')
    @mock.patch('crmsh.bootstrap.status')
    def test_init_qdevice_already_configured(self, mock_status, mock_ssh, mock_qdevice_configured, mock_confirm, mock_qdevice_start):
        bootstrap._context = mock.Mock(qdevice_inst=self.qdevice_with_ip)
        mock_ssh.return_value = False
        mock_qdevice_configured.return_value = True
        mock_confirm.return_value = False

        bootstrap.init_qdevice()

        mock_status.assert_called_once_with("\nConfigure Qdevice/Qnetd:")
        mock_ssh.assert_called_once_with("10.10.10.123")
        mock_qdevice_configured.assert_called_once_with()
        mock_confirm.assert_called_once_with("Qdevice is already configured - overwrite?")
        mock_qdevice_start.assert_called_once_with()

    @mock.patch('crmsh.bootstrap.start_qdevice_service')
    @mock.patch('crmsh.bootstrap.status_done')
    @mock.patch('crmsh.corosync.QDevice.certificate_process_on_init')
    @mock.patch('crmsh.bootstrap.status_long')
    @mock.patch('crmsh.utils.is_qdevice_tls_on')
    @mock.patch('crmsh.bootstrap.config_qdevice')
    @mock.patch('crmsh.corosync.QDevice.valid_qnetd')
    @mock.patch('crmsh.utils.is_qdevice_configured')
    @mock.patch('crmsh.utils.check_ssh_passwd_need')
    @mock.patch('crmsh.bootstrap.status')
    def test_init_qdevice(self, mock_status, mock_ssh, mock_qdevice_configured, mock_valid_qnetd, mock_config_qdevice,
            mock_tls, mock_status_long, mock_certificate, mock_status_done, mock_start_qdevice):
        bootstrap._context = mock.Mock(qdevice_inst=self.qdevice_with_ip)
        mock_ssh.return_value = False
        mock_qdevice_configured.return_value = False
        mock_tls.return_value = True

        bootstrap.init_qdevice()

        mock_status.assert_called_once_with("\nConfigure Qdevice/Qnetd:")
        mock_ssh.assert_called_once_with("10.10.10.123")
        mock_valid_qnetd.assert_called_once_with()
        mock_qdevice_configured.assert_called_once_with()
        mock_config_qdevice.assert_called_once_with()
        mock_tls.assert_called_once_with()
        mock_status_long.assert_called_once_with("Qdevice certification process")
        mock_certificate.assert_called_once_with()
        mock_status_done.assert_called_once_with()
        mock_start_qdevice.assert_called_once_with()

    @mock.patch('crmsh.corosync.QDevice.start_qnetd')
    @mock.patch('crmsh.corosync.QDevice.enable_qnetd')
    @mock.patch('crmsh.utils.cluster_run_cmd')
    @mock.patch('crmsh.bootstrap.status')
    def test_start_qdevice_service(self, mock_status, mock_cluster_run, mock_enable_qnetd, mock_start_qnetd):
        bootstrap._context = mock.Mock(qdevice_inst=self.qdevice_with_ip)

        bootstrap.start_qdevice_service()

        mock_status.assert_has_calls([
            mock.call("Enable corosync-qdevice.service in cluster"),
            mock.call("Starting corosync-qdevice.service in cluster"),
            mock.call("Enable corosync-qnetd.service on 10.10.10.123"),
            mock.call("Starting corosync-qnetd.service on 10.10.10.123")
            ])
        mock_cluster_run.assert_has_calls([
            mock.call("systemctl enable corosync-qdevice"),
            mock.call("systemctl start corosync-qdevice")
            ])
        mock_enable_qnetd.assert_called_once_with()
        mock_start_qnetd.assert_called_once_with()

    @mock.patch('crmsh.bootstrap.status_done')
    @mock.patch('crmsh.utils.cluster_run_cmd')
    @mock.patch('crmsh.bootstrap.update_expected_votes')
    @mock.patch('crmsh.bootstrap.status_long')
    @mock.patch('crmsh.corosync.add_nodelist_from_cmaptool')
    @mock.patch('crmsh.corosync.is_unicast')
    @mock.patch('crmsh.corosync.QDevice.write_qdevice_config')
    @mock.patch('crmsh.corosync.QDevice.remove_qdevice_db')
    def test_config_qdevice(self, mock_remove_qdevice_db, mock_write_qdevice_config, mock_is_unicast,
            mock_add_nodelist, mock_status_long, mock_update_votes, mock_cluster_run, mock_status_done):
        bootstrap._context = mock.Mock(qdevice_inst=self.qdevice_with_ip)
        mock_is_unicast.return_value = False

        bootstrap.config_qdevice()

        mock_remove_qdevice_db.assert_called_once_with()
        mock_write_qdevice_config.assert_called_once_with()
        mock_is_unicast.assert_called_once_with()
        mock_add_nodelist.assert_called_once_with()
        mock_status_long.assert_called_once_with("Update configuration")
        mock_update_votes.assert_called_once_with()
        mock_cluster_run.assert_called_once_with("crm corosync reload")
        mock_status_done.assert_called_once_with()

    @mock.patch('crmsh.bootstrap.error')
    @mock.patch('crmsh.utils.is_qdevice_configured')
    def test_remove_qdevice_no_configured(self, mock_qdevice_configured, mock_error):
        mock_qdevice_configured.return_value = False
        mock_error.side_effect = SystemExit

        with self.assertRaises(SystemExit):
            bootstrap.remove_qdevice()

        mock_qdevice_configured.assert_called_once_with()
        mock_error.assert_called_once_with("No QDevice configuration in this cluster")

    @mock.patch('crmsh.bootstrap.confirm')
    @mock.patch('crmsh.utils.is_qdevice_configured')
    def test_remove_qdevice_not_confirmed(self, mock_qdevice_configured, mock_confirm):
        mock_qdevice_configured.return_value = True
        mock_confirm.return_value = False

        bootstrap.remove_qdevice()

        mock_qdevice_configured.assert_called_once_with()
        mock_confirm.assert_called_once_with("Removing QDevice service and configuration from cluster: Are you sure?")

    @mock.patch('crmsh.bootstrap.status_done')
    @mock.patch('crmsh.bootstrap.update_expected_votes')
    @mock.patch('crmsh.corosync.QDevice')
    @mock.patch('crmsh.corosync.get_value')
    @mock.patch('crmsh.bootstrap.status_long')
    @mock.patch('crmsh.bootstrap.invoke')
    @mock.patch('crmsh.bootstrap.status')
    @mock.patch('crmsh.bootstrap.confirm')
    @mock.patch('crmsh.utils.is_qdevice_configured')
    def test_remove_qdevice(self, mock_qdevice_configured, mock_confirm, mock_status, mock_invoke,
            mock_status_long, mock_get_value, mock_qdevice, mock_update_votes, mock_status_done):
        mock_qdevice_configured.return_value = True
        mock_confirm.return_value = True
        mock_get_value.return_value = "10.10.10.123"
        mock_qdevice_inst = mock.Mock()
        mock_qdevice.return_value = mock_qdevice_inst
        mock_qdevice_inst.remove_qdevice_config = mock.Mock()
        mock_qdevice_inst.remove_qdevice_db = mock.Mock()

        bootstrap.remove_qdevice()

        mock_qdevice_configured.assert_called_once_with()
        mock_confirm.assert_called_once_with("Removing QDevice service and configuration from cluster: Are you sure?")
        mock_status.assert_has_calls([
            mock.call("Disable corosync-qdevice.service"),
            mock.call("Stopping corosync-qdevice.service")
            ])
        mock_invoke.assert_has_calls([
            mock.call("crm cluster run 'systemctl disable corosync-qdevice'"),
            mock.call("crm cluster run 'systemctl stop corosync-qdevice'"),
            mock.call("crm cluster run 'crm corosync reload'")
            ] )
        mock_status_long.assert_called_once_with("Removing QDevice configuration from cluster")
        mock_get_value.assert_called_once_with("quorum.device.net.host")
        mock_qdevice.assert_called_once_with("10.10.10.123")
        mock_qdevice_inst.remove_qdevice_config.assert_called_once_with()
        mock_qdevice_inst.remove_qdevice_db.assert_called_once_with()
        mock_update_votes.assert_called_once_with()
        mock_status_done.assert_called_once_with()

    @mock.patch('crmsh.bootstrap.status_done')
    @mock.patch('crmsh.utils.start_service')
    @mock.patch('crmsh.corosync.QDevice')
    @mock.patch('crmsh.corosync.get_value')
    @mock.patch('crmsh.utils.is_qdevice_tls_on')
    @mock.patch('crmsh.bootstrap.invoke')
    @mock.patch('crmsh.bootstrap.csync2_update')
    @mock.patch('crmsh.corosync.conf')
    @mock.patch('crmsh.corosync.add_nodelist_from_cmaptool')
    @mock.patch('crmsh.corosync.is_unicast')
    @mock.patch('crmsh.bootstrap.status_long')
    def test_start_qdevice_on_join_node(self, mock_status_long, mock_is_unicast, mock_add_nodelist,
            mock_conf, mock_csync2_update, mock_invoke, mock_qdevice_tls,
            mock_get_value, mock_qdevice, mock_start_service, mock_status_done):
        mock_is_unicast.return_value = False
        mock_qdevice_tls.return_value = True
        mock_conf.return_value = "corosync.conf"
        mock_get_value.return_value = "10.10.10.123"
        mock_qdevice_inst = mock.Mock()
        mock_qdevice.return_value = mock_qdevice_inst
        mock_qdevice_inst.certificate_process_on_join = mock.Mock()

        bootstrap.start_qdevice_on_join_node("node2")

        mock_status_long.assert_called_once_with("Starting corosync-qdevice.service")
        mock_is_unicast.assert_called_once_with()
        mock_add_nodelist.assert_called_once_with()
        mock_conf.assert_called_once_with()
        mock_csync2_update.assert_called_once_with("corosync.conf")
        mock_invoke.assert_called_once_with("crm corosync reload")
        mock_qdevice_tls.assert_called_once_with()
        mock_get_value.assert_called_once_with("quorum.device.net.host")
        mock_qdevice.assert_called_once_with("10.10.10.123", cluster_node="node2")
        mock_qdevice_inst.certificate_process_on_join.assert_called_once_with()
        mock_start_service.assert_called_once_with("corosync-qdevice.service", enable=True)
        mock_status_done.assert_called_once_with()

    @mock.patch('crmsh.utils.get_stdout_stderr')
    @mock.patch('crmsh.bootstrap.log')
    def test_invoke(self, mock_log, mock_run):
        mock_run.return_value = (0, "output", "error")
        res = bootstrap.invoke("cmd --option")
        self.assertEqual(res, (True, "output", "error"))
        mock_log.assert_has_calls([
            mock.call('+ cmd --option'),
            mock.call('output'),
            mock.call('error')
            ])

    @mock.patch('crmsh.bootstrap.invoke')
    def test_invokerc(self, mock_invoke):
        mock_invoke.return_value = (True, None, None)
        res = bootstrap.invokerc("cmd")
        self.assertEqual(res, True)
        mock_invoke.assert_called_once_with("cmd")


class TestValidation(unittest.TestCase):
    """
    Unitary tests for class bootstrap.Validation
    """
    @classmethod
    def setUpClass(cls):
        """
        Global setUp.
        """

    def setUp(self):
        """
        Test setUp.
        """
        self.validate_inst = bootstrap.Validation("10.10.10.1")
        self.validate_port_inst_in_use = bootstrap.Validation("4567", ["4568"])
        self.validate_port_inst_out_of_range = bootstrap.Validation("456766")

    def tearDown(self):
        """
        Test tearDown.
        """

    @classmethod
    def tearDownClass(cls):
        """
        Global tearDown.
        """

    @mock.patch('crmsh.utils.IP.is_mcast')
    def test_is_mcast_addr(self, mock_mcast):
        mock_mcast.return_value = False
        with self.assertRaises(ValueError) as err:
            self.validate_inst._is_mcast_addr()
        self.assertEqual("10.10.10.1 is not multicast address", str(err.exception))
        mock_mcast.assert_called_once_with("10.10.10.1")

    def test_is_local_addr(self):
        with self.assertRaises(ValueError) as err:
            self.validate_inst._is_local_addr(["20.20.20.1", "20.20.20.2"])
        self.assertEqual("Address must be a local address (one of ['20.20.20.1', '20.20.20.2'])", str(err.exception))

    def test_is_valid_port_in_use(self):
        with self.assertRaises(ValueError) as err:
            self.validate_port_inst_in_use._is_valid_port()
        self.assertEqual("Port 4567 is already in use by corosync. Leave a gap between multiple rings.", str(err.exception))

    def test_is_valid_port_out_of_range(self):
        with self.assertRaises(ValueError) as err:
            self.validate_port_inst_out_of_range._is_valid_port()
        self.assertEqual("Valid port range should be 1025-65535", str(err.exception))

    @mock.patch('crmsh.bootstrap.Validation._is_mcast_addr')
    def test_valid_mcast_address(self, mock_mcast):
        bootstrap.Validation.valid_mcast_address("10.10.10.1")
        mock_mcast.assert_called_once_with()

    @mock.patch('crmsh.bootstrap.Validation._is_local_addr')
    def test_valid_ucast_ip(self, mock_local_addr):
        bootstrap._context = mock.Mock(local_ip_list=["10.10.10.2", "10.10.10.3"])
        bootstrap.Validation.valid_ucast_ip("10.10.10.1")
        mock_local_addr.assert_called_once_with(["10.10.10.2", "10.10.10.3"])
    
    @mock.patch('crmsh.bootstrap.Validation._is_local_addr')
    def test_valid_mcast_ip(self, mock_local_addr):
        bootstrap._context = mock.Mock(local_ip_list=["10.10.10.2", "10.10.10.3"],
                local_network_list=["10.10.10.0"])
        bootstrap.Validation.valid_mcast_ip("10.10.10.1")
        mock_local_addr.assert_called_once_with(["10.10.10.2", "10.10.10.3", "10.10.10.0"])

    @mock.patch('crmsh.bootstrap.Validation._is_valid_port')
    def test_valid_port(self, mock_port):
        bootstrap.Validation.valid_port("10.10.10.1")
        mock_port.assert_called_once_with()

    @mock.patch('crmsh.bootstrap.invokerc')
    @mock.patch('crmsh.utils.IP.is_ipv6')
    def test_valid_admin_ip_in_use(self, mock_ipv6, mock_invoke):
        mock_ipv6.return_value = False
        mock_invoke.return_value = True

        with self.assertRaises(ValueError) as err:
            self.validate_inst.valid_admin_ip("10.10.10.1")
        self.assertEqual("Address already in use: 10.10.10.1", str(err.exception))

        mock_ipv6.assert_called_once_with("10.10.10.1")
        mock_invoke.assert_called_once_with("ping -c 1 10.10.10.1")

    @mock.patch('crmsh.bootstrap.error')
    @mock.patch('crmsh.utils.service_is_active')
    @mock.patch('crmsh.bootstrap.init')
    @mock.patch('crmsh.bootstrap.Context')
    def test_bootstrap_remove_cluster_is_active(self, mock_context, mock_init, mock_active,
            mock_error):
        mock_context_inst = mock.Mock()
        mock_context.return_value = mock_context_inst
        mock_active.return_value = False
        mock_error.side_effect = SystemExit

        with self.assertRaises(SystemExit):
             bootstrap.bootstrap_remove(mock_context_inst)

        mock_init.assert_called_once_with()
        mock_active.assert_called_once_with("corosync.service")
        mock_error.assert_called_once_with("Cluster is not active - can't execute removing action")

    @mock.patch('crmsh.bootstrap.remove_qdevice')
    @mock.patch('crmsh.bootstrap.error')
    @mock.patch('crmsh.utils.service_is_active')
    @mock.patch('crmsh.bootstrap.init')
    @mock.patch('crmsh.bootstrap.Context')
    def test_bootstrap_remove_qdevice(self, mock_context, mock_init, mock_active,
            mock_error, mock_qdevice):
        mock_context_inst = mock.Mock(qdevice=True, cluster_node=None)
        mock_context.return_value = mock_context_inst
        mock_active.return_value = True

        bootstrap.bootstrap_remove(mock_context_inst)

        mock_init.assert_called_once_with()
        mock_active.assert_called_once_with("corosync.service")
        mock_error.assert_not_called()
        mock_qdevice.assert_called_once_with()

    @mock.patch('crmsh.bootstrap.error')
    @mock.patch('crmsh.utils.service_is_active')
    @mock.patch('crmsh.bootstrap.init')
    @mock.patch('crmsh.bootstrap.Context')
    def test_bootstrap_remove_qdevice_cluster_node(self, mock_context, mock_init, mock_active, mock_error):
        mock_context_inst = mock.Mock(qdevice=True, cluster_node="node1")
        mock_context.return_value = mock_context_inst
        mock_active.return_value = True
        mock_error.side_effect = SystemExit

        with self.assertRaises(SystemExit):
            bootstrap.bootstrap_remove(mock_context_inst)

        mock_init.assert_called_once_with()
        mock_active.assert_called_once_with("corosync.service")
        mock_error.assert_called_once_with("Either remove node or qdevice")

    @mock.patch('crmsh.bootstrap.prompt_for_string')
    @mock.patch('crmsh.bootstrap.status')
    @mock.patch('crmsh.bootstrap.remove_qdevice')
    @mock.patch('crmsh.bootstrap.error')
    @mock.patch('crmsh.utils.service_is_active')
    @mock.patch('crmsh.bootstrap.init')
    @mock.patch('crmsh.bootstrap.Context')
    def test_bootstrap_remove_no_cluster_node(self, mock_context, mock_init, mock_active,
            mock_error, mock_qdevice, mock_status, mock_prompt):
        mock_context_inst = mock.Mock(yes_to_all=False, cluster_node=None, qdevice_rm_flag=None)
        mock_context.return_value = mock_context_inst
        mock_active.return_value = True
        mock_prompt.return_value = None
        mock_error.side_effect = SystemExit

        with self.assertRaises(SystemExit):
            bootstrap.bootstrap_remove(mock_context_inst)

        mock_init.assert_called_once_with()
        mock_active.assert_called_once_with("corosync.service")
        mock_qdevice.assert_not_called()
        mock_status.assert_called_once_with('Remove This Node from Cluster:\n  You will be asked for the IP address or name of an existing node,\n  which will be removed from the cluster. This command must be\n  executed from a different node in the cluster.\n')
        mock_prompt.assert_called_once_with("IP address or hostname of cluster node (e.g.: 192.168.1.1)", ".+")
        mock_error.assert_called_once_with("No existing IP/hostname specified (use -c option)")

    @mock.patch('crmsh.bootstrap.confirm')
    @mock.patch('crmsh.bootstrap.get_cluster_node_hostname')
    @mock.patch('crmsh.bootstrap.remove_qdevice')
    @mock.patch('crmsh.bootstrap.error')
    @mock.patch('crmsh.utils.service_is_active')
    @mock.patch('crmsh.bootstrap.init')
    @mock.patch('crmsh.bootstrap.Context')
    def test_bootstrap_remove_no_confirm(self, mock_context, mock_init, mock_active,
            mock_error, mock_qdevice, mock_hostname, mock_confirm):
        mock_context_inst = mock.Mock(cluster_node="node1", force=False, qdevice_rm_flag=None)
        mock_context.return_value = mock_context_inst
        mock_active.return_value = True
        mock_hostname.return_value = "node1"
        mock_confirm.return_value = False

        bootstrap.bootstrap_remove(mock_context_inst)

        mock_init.assert_called_once_with()
        mock_active.assert_called_once_with("corosync.service")
        mock_qdevice.assert_not_called()
        mock_error.assert_not_called()
        mock_hostname.assert_called_once_with()
        mock_confirm.assert_called_once_with('Removing node "node1" from the cluster: Are you sure?')

    @mock.patch('crmsh.utils.this_node')
    @mock.patch('crmsh.bootstrap.confirm')
    @mock.patch('crmsh.bootstrap.get_cluster_node_hostname')
    @mock.patch('crmsh.bootstrap.remove_qdevice')
    @mock.patch('crmsh.bootstrap.error')
    @mock.patch('crmsh.utils.service_is_active')
    @mock.patch('crmsh.bootstrap.init')
    @mock.patch('crmsh.bootstrap.Context')
    def test_bootstrap_remove_self_need_force(self, mock_context, mock_init, mock_active,
            mock_error, mock_qdevice, mock_hostname, mock_confirm, mock_this_node):
        mock_context_inst = mock.Mock(cluster_node="node1", force=False, qdevice_rm_flag=None)
        mock_context.return_value = mock_context_inst
        mock_active.return_value = True
        mock_hostname.return_value = "node1"
        mock_confirm.return_value = True
        mock_this_node.return_value = "node1"
        mock_error.side_effect = SystemExit

        with self.assertRaises(SystemExit):
            bootstrap.bootstrap_remove(mock_context_inst)

        mock_init.assert_called_once_with()
        mock_active.assert_called_once_with("corosync.service")
        mock_qdevice.assert_not_called()
        mock_hostname.assert_called_once_with()
        mock_confirm.assert_called_once_with('Removing node "node1" from the cluster: Are you sure?')
        mock_this_node.assert_called_once_with()
        mock_error.assert_called_once_with("Removing self requires --force")

    @mock.patch('crmsh.bootstrap.remove_self')
    @mock.patch('crmsh.utils.this_node')
    @mock.patch('crmsh.bootstrap.confirm')
    @mock.patch('crmsh.bootstrap.get_cluster_node_hostname')
    @mock.patch('crmsh.bootstrap.remove_qdevice')
    @mock.patch('crmsh.bootstrap.error')
    @mock.patch('crmsh.utils.service_is_active')
    @mock.patch('crmsh.bootstrap.init')
    @mock.patch('crmsh.bootstrap.Context')
    def test_bootstrap_remove_self(self, mock_context, mock_init, mock_active,
            mock_error, mock_qdevice, mock_hostname, mock_confirm, mock_this_node, mock_self):
        mock_context_inst = mock.Mock(cluster_node="node1", force=True, qdevice_rm_flag=None)
        mock_context.return_value = mock_context_inst
        mock_active.return_value = True
        mock_hostname.return_value = "node1"
        mock_this_node.return_value = "node1"

        bootstrap.bootstrap_remove(mock_context_inst)

        mock_init.assert_called_once_with()
        mock_active.assert_called_once_with("corosync.service")
        mock_qdevice.assert_not_called()
        mock_hostname.assert_called_once_with()
        mock_confirm.assert_not_called()
        mock_this_node.assert_called_once_with()
        mock_error.assert_not_called()
        mock_self.assert_called_once_with()

    @mock.patch('crmsh.xmlutil.listnodes')
    @mock.patch('crmsh.utils.this_node')
    @mock.patch('crmsh.bootstrap.confirm')
    @mock.patch('crmsh.bootstrap.get_cluster_node_hostname')
    @mock.patch('crmsh.bootstrap.remove_qdevice')
    @mock.patch('crmsh.bootstrap.error')
    @mock.patch('crmsh.utils.service_is_active')
    @mock.patch('crmsh.bootstrap.init')
    @mock.patch('crmsh.bootstrap.Context')
    def test_bootstrap_remove_not_in_cluster(self, mock_context, mock_init, mock_active,
            mock_error, mock_qdevice, mock_hostname, mock_confirm, mock_this_node, mock_list):
        mock_context_inst = mock.Mock(cluster_node="node2", force=True, qdevice_rm_flag=None)
        mock_context.return_value = mock_context_inst
        mock_active.return_value = True
        mock_hostname.return_value = "node2"
        mock_this_node.return_value = "node1"
        mock_list.return_value = ["node1", "node3"]
        mock_error.side_effect = SystemExit

        with self.assertRaises(SystemExit):
            bootstrap.bootstrap_remove(mock_context_inst)

        mock_init.assert_called_once_with()
        mock_active.assert_called_once_with("corosync.service")
        mock_qdevice.assert_not_called()
        mock_hostname.assert_called_once_with()
        mock_confirm.assert_not_called()
        mock_this_node.assert_called_once_with()
        mock_error.assert_called_once_with("Specified node node2 is not configured in cluster! Unable to remove.")

    @mock.patch('crmsh.bootstrap.remove_node_from_cluster')
    @mock.patch('crmsh.xmlutil.listnodes')
    @mock.patch('crmsh.utils.this_node')
    @mock.patch('crmsh.bootstrap.confirm')
    @mock.patch('crmsh.bootstrap.get_cluster_node_hostname')
    @mock.patch('crmsh.bootstrap.remove_qdevice')
    @mock.patch('crmsh.bootstrap.error')
    @mock.patch('crmsh.utils.service_is_active')
    @mock.patch('crmsh.bootstrap.init')
    @mock.patch('crmsh.bootstrap.Context')
    def test_bootstrap_remove(self, mock_context, mock_init, mock_active,
            mock_error, mock_qdevice, mock_hostname, mock_confirm, mock_this_node,
            mock_list, mock_remove):
        mock_context_inst = mock.Mock(cluster_node="node2", qdevice_rm_flag=None, force=True)
        mock_context.return_value = mock_context_inst
        mock_active.return_value = True
        mock_hostname.return_value = "node2"
        mock_this_node.return_value = "node1"
        mock_list.return_value = ["node1", "node2"]

        bootstrap.bootstrap_remove(mock_context_inst)

        mock_init.assert_called_once_with()
        mock_active.assert_called_once_with("corosync.service")
        mock_qdevice.assert_not_called()
        mock_hostname.assert_called_once_with()
        mock_confirm.assert_not_called()
        mock_this_node.assert_called_once_with()
        mock_error.assert_not_called()
        mock_remove.assert_called_once_with()

    @mock.patch('crmsh.bootstrap.error')
    @mock.patch('crmsh.utils.is_qdevice_configured')
    def test_remove_qdevice_not_configured(self, mock_configured, mock_error):
        mock_configured.return_value = False
        mock_error.side_effect = SystemExit

        with self.assertRaises(SystemExit):
            bootstrap.remove_qdevice()

        mock_configured.assert_called_once_with()
        mock_error.assert_called_once_with("No QDevice configuration in this cluster")

    @mock.patch('crmsh.bootstrap.confirm')
    @mock.patch('crmsh.utils.is_qdevice_configured')
    def test_remove_qdevice_not_confrim(self, mock_configured, mock_confirm):
        mock_configured.return_value = True
        mock_confirm.return_value = False

        bootstrap.remove_qdevice()

        mock_configured.assert_called_once_with()
        mock_confirm.assert_called_once_with("Removing QDevice service and configuration from cluster: Are you sure?")

    @mock.patch('crmsh.bootstrap.status_done')
    @mock.patch('crmsh.bootstrap.update_expected_votes')
    @mock.patch('crmsh.corosync.QDevice')
    @mock.patch('crmsh.corosync.get_value')
    @mock.patch('crmsh.bootstrap.status_long')
    @mock.patch('crmsh.bootstrap.invoke')
    @mock.patch('crmsh.bootstrap.status')
    @mock.patch('crmsh.bootstrap.confirm')
    @mock.patch('crmsh.utils.is_qdevice_configured')
    def test_remove_qdevice(self, mock_configured, mock_confirm, mock_status, mock_invoke,
            mock_long, mock_get_value, mock_qdevice, mock_expected, mock_done):
        mock_configured.return_value = True
        mock_confirm.return_value = True
        mock_get_value.return_value = "node1"
        mock_qdevice_inst = mock.Mock()
        mock_qdevice.return_value = mock_qdevice_inst

        bootstrap.remove_qdevice()

        mock_configured.assert_called_once_with()
        mock_confirm.assert_called_once_with("Removing QDevice service and configuration from cluster: Are you sure?")
        mock_status.assert_has_calls([
            mock.call("Disable corosync-qdevice.service"),
            mock.call("Stopping corosync-qdevice.service")
            ])
        mock_invoke.assert_has_calls([
            mock.call("crm cluster run 'systemctl disable corosync-qdevice'"),
            mock.call("crm cluster run 'systemctl stop corosync-qdevice'"),
            mock.call("crm cluster run 'crm corosync reload'")
            ])
        mock_long.assert_called_once_with("Removing QDevice configuration from cluster")
        mock_get_value.assert_called_once_with("quorum.device.net.host")
        mock_qdevice.assert_called_once_with("node1")
        mock_qdevice_inst.remove_qdevice_config.assert_called_once_with()
        mock_qdevice_inst.remove_qdevice_db.assert_called_once_with()
        mock_expected.assert_called_once_with()
        mock_done.assert_called_once_with()

    @mock.patch('crmsh.bootstrap.error')
    @mock.patch('crmsh.utils.ext_cmd_nosudo')
    @mock.patch('crmsh.xmlutil.listnodes')
    def test_remove_self_other_nodes(self, mock_list, mock_ext, mock_error):
        mock_list.return_value = ["node1", "node2"]
        mock_ext.return_value = 1
        mock_error.side_effect = SystemExit

        with self.assertRaises(SystemExit):
            bootstrap._context = mock.Mock(cluster_node="node1", yes_to_all=True)
            bootstrap.remove_self()

        mock_list.assert_called_once_with(include_remote_nodes=False)
        mock_ext.assert_called_once_with("ssh -o StrictHostKeyChecking=no node2 'crm cluster remove -y -c node1'")
        mock_error.assert_called_once_with("Failed to remove this node from node2")

    @mock.patch('crmsh.bootstrap.error')
    @mock.patch('crmsh.bootstrap.invokerc')
    @mock.patch('crmsh.bootstrap.stop_services')
    @mock.patch('crmsh.xmlutil.listnodes')
    def test_remove_self_rm_failed(self, mock_list, mock_stop_service, mock_invoke, mock_error):
        mock_list.return_value = ["node1"]
        mock_invoke.return_value = False
        mock_error.side_effect = SystemExit

        with self.assertRaises(SystemExit):
            bootstrap._context = mock.Mock(cluster_node="node1", yes_to_all=True, rm_list=["file1", "file2"])
            bootstrap.remove_self()

        mock_list.assert_called_once_with(include_remote_nodes=False)
        mock_stop_service.assert_called_once_with(bootstrap.SERVICES_STOP_LIST)
        mock_invoke.assert_called_once_with('bash -c "rm -f file1 file2"')
        mock_error.assert_called_once_with("Deleting the configuration files failed")

    @mock.patch('crmsh.utils.get_iplist_from_name')
    @mock.patch('crmsh.corosync.get_values')
    def test_set_cluster_node_ip_host(self, mock_get_values, mock_get_iplist):
        mock_get_values.return_value = ["node1", "node2"]
        bootstrap._context = mock.Mock(cluster_node="node1")
        bootstrap.set_cluster_node_ip()
        mock_get_values.assert_called_once_with("nodelist.node.ring0_addr")
        mock_get_iplist.assert_not_called()

    @mock.patch('crmsh.utils.get_iplist_from_name')
    @mock.patch('crmsh.corosync.get_values')
    def test_set_cluster_node_ip(self, mock_get_values, mock_get_iplist):
        mock_get_values.return_value = ["10.10.10.1", "10.10.10.2"]
        mock_get_iplist.return_value = ["10.10.10.1"]
        bootstrap._context = mock.Mock(cluster_node="node1")
        bootstrap.set_cluster_node_ip()
        mock_get_values.assert_called_once_with("nodelist.node.ring0_addr")
        mock_get_iplist.assert_called_once_with('node1')

    @mock.patch('crmsh.utils.stop_service')
    @mock.patch('crmsh.bootstrap.status')
    @mock.patch('crmsh.utils.service_is_active')
    def test_stop_services(self, mock_active, mock_status, mock_stop):
        mock_active.side_effect = [True, True, True]
        bootstrap.stop_services(bootstrap.SERVICES_STOP_LIST)
        mock_active.assert_has_calls([
            mock.call("corosync-qdevice.service", remote_addr=None),
            mock.call("corosync.service", remote_addr=None),
            mock.call("hawk.service", remote_addr=None)
            ])
        mock_status.assert_has_calls([
            mock.call("Stopping the corosync-qdevice.service"),
            mock.call("Stopping the corosync.service"),
            mock.call("Stopping the hawk.service")
            ])
        mock_stop.assert_has_calls([
            mock.call("corosync-qdevice.service", disable=True, remote_addr=None),
            mock.call("corosync.service", disable=True, remote_addr=None),
            mock.call("hawk.service", disable=True, remote_addr=None)
            ])

    @mock.patch('crmsh.bootstrap.error')
    @mock.patch('crmsh.bootstrap.invoke')
    @mock.patch('crmsh.bootstrap.stop_services')
    @mock.patch('crmsh.bootstrap.set_cluster_node_ip')
    def test_remove_node_from_cluster_rm_failed(self, mock_get_ip, mock_stop, mock_invoke, mock_error):
        mock_invoke.return_value = (False, None, "error")
        mock_error.side_effect = SystemExit

        with self.assertRaises(SystemExit):
            bootstrap._context = mock.Mock(cluster_node="node1", rm_list=["file1", "file2"])
            bootstrap.remove_node_from_cluster()

        mock_get_ip.assert_called_once_with()
        mock_stop.assert_called_once_with(bootstrap.SERVICES_STOP_LIST, remote_addr="node1")
        mock_invoke.assert_called_once_with('ssh -o StrictHostKeyChecking=no root@node1 "bash -c \\"rm -f file1 file2\\""')
        mock_error.assert_called_once_with("Deleting the configuration files failed: error")

    @mock.patch('crmsh.bootstrap.error')
    @mock.patch('crmsh.bootstrap.invokerc')
    @mock.patch('crmsh.bootstrap.invoke')
    @mock.patch('crmsh.bootstrap.status')
    @mock.patch('crmsh.bootstrap.stop_services')
    @mock.patch('crmsh.bootstrap.set_cluster_node_ip')
    def test_remove_node_from_cluster_rm_node_failed(self, mock_get_ip, mock_stop, mock_status, mock_invoke, mock_invokerc, mock_error):
        mock_invoke.return_value = (True, None, None)
        mock_invokerc.return_value = False
        mock_error.side_effect = SystemExit

        with self.assertRaises(SystemExit):
            bootstrap._context = mock.Mock(cluster_node="node1", rm_list=["file1", "file2"])
            bootstrap.remove_node_from_cluster()

        mock_get_ip.assert_called_once_with()
        mock_status.assert_called_once_with("Removing the node node1")
        mock_stop.assert_called_once_with(bootstrap.SERVICES_STOP_LIST, remote_addr="node1")
        mock_invoke.assert_called_once_with('ssh -o StrictHostKeyChecking=no root@node1 "bash -c \\"rm -f file1 file2\\""')
        mock_invokerc.assert_called_once_with("crm node delete node1")
        mock_error.assert_called_once_with("Failed to remove node1")

    @mock.patch('crmsh.bootstrap.error')
    @mock.patch('crmsh.bootstrap.invokerc')
    @mock.patch('crmsh.bootstrap.invoke')
    @mock.patch('crmsh.bootstrap.status')
    @mock.patch('crmsh.bootstrap.stop_services')
    @mock.patch('crmsh.bootstrap.set_cluster_node_ip')
    def test_remove_node_from_cluster_rm_csync_failed(self, mock_get_ip, mock_stop, mock_status, mock_invoke, mock_invokerc, mock_error):
        mock_invoke.return_value = (True, None, None)
        mock_invokerc.side_effect = [True, False]
        mock_error.side_effect = SystemExit

        with self.assertRaises(SystemExit):
            bootstrap._context = mock.Mock(cluster_node="node1", rm_list=["file1", "file2"])
            bootstrap.remove_node_from_cluster()

        mock_get_ip.assert_called_once_with()
        mock_status.assert_called_once_with("Removing the node node1")
        mock_stop.assert_called_once_with(bootstrap.SERVICES_STOP_LIST, remote_addr="node1")
        mock_invoke.assert_called_once_with('ssh -o StrictHostKeyChecking=no root@node1 "bash -c \\"rm -f file1 file2\\""')
        mock_invokerc.assert_has_calls([
            mock.call('crm node delete node1'),
            mock.call("sed -i /node1/d {}".format(bootstrap.CSYNC2_CFG))
            ])
        mock_error.assert_called_once_with("Removing the node node1 from {} failed".format(bootstrap.CSYNC2_CFG))

    @mock.patch('crmsh.bootstrap.csync2_update')
    @mock.patch('crmsh.bootstrap.decrease_expected_votes')
    @mock.patch('crmsh.corosync.del_node')
    @mock.patch('crmsh.corosync.get_values')
    @mock.patch('crmsh.bootstrap.error')
    @mock.patch('crmsh.bootstrap.invokerc')
    @mock.patch('crmsh.bootstrap.invoke')
    @mock.patch('crmsh.bootstrap.status')
    @mock.patch('crmsh.bootstrap.stop_services')
    @mock.patch('crmsh.bootstrap.set_cluster_node_ip')
    def test_remove_node_from_cluster_hostname(self, mock_get_ip, mock_stop, mock_status,
            mock_invoke, mock_invokerc, mock_error, mock_get_values, mock_del, mock_decrease, mock_csync2):
        mock_invoke.side_effect = [(True, None, None), (True, None, None)]
        mock_invokerc.side_effect = [True, True]
        mock_get_values.return_value = ["10.10.10.1"]

        bootstrap._context = mock.Mock(cluster_node="node1", cluster_node_ip=None, rm_list=["file1", "file2"])
        bootstrap.remove_node_from_cluster()

        mock_get_ip.assert_called_once_with()
        mock_status.assert_has_calls([
            mock.call("Removing the node node1"),
            mock.call("Propagating configuration changes across the remaining nodes")
            ])
        mock_stop.assert_called_once_with(bootstrap.SERVICES_STOP_LIST, remote_addr="node1")
        mock_invoke.assert_has_calls([
            mock.call('ssh -o StrictHostKeyChecking=no root@node1 "bash -c \\"rm -f file1 file2\\""'),
            mock.call("corosync-cfgtool -R")
            ])
        mock_invokerc.assert_has_calls([
            mock.call('crm node delete node1'),
            mock.call("sed -i /node1/d {}".format(bootstrap.CSYNC2_CFG))
            ])
        mock_error.assert_not_called()
        mock_get_values.assert_called_once_with("nodelist.node.ring0_addr")
        mock_del.assert_called_once_with("node1")
        mock_decrease.assert_called_once_with()
        mock_csync2.assert_has_calls([
            mock.call(bootstrap.CSYNC2_CFG),
            mock.call("/etc/corosync/corosync.conf")
            ])
