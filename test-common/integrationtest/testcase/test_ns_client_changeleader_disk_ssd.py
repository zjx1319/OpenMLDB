# -*- coding: utf-8 -*-
from testcasebase import TestCaseBase
import time
import os
from libs.test_loader import load
import libs.utils as utils
from libs.logger import infoLogger
from libs.deco import multi_dimension
import libs.ddt as ddt
import libs.conf as conf
@ddt.ddt
@multi_dimension(False)
class TestChangeLeader(TestCaseBase):
    @ddt.data(
        ['kSSD'],
        ['kHDD'],
    )
    @ddt.unpack
    def test_changeleader_master_disconnect(self,storage_mode):
        """
        changeleader功能正常，主节点断网后，可以手工故障切换，切换成功后从节点可以同步数据
        :return:
        """
        self.start_client(self.leader)
        metadata_path = '{}/metadata.txt'.format(self.testpath)
        name = 'tname{}'.format(time.time())
        infoLogger.info(name)
        table_meta = {
            "name": name,
            "ttl": 144000,
            "storage_mode": storage_mode,
            "table_partition": [
                {"endpoint": self.leader,"pid_group": "0-2","is_leader": "true"},
                {"endpoint": self.slave1,"pid_group": "0-1","is_leader": "false"},
                {"endpoint": self.slave2,"pid_group": "0-2","is_leader": "false"},
            ],
            "column_desc":[
                {"name": "k1", "type": "string", "add_ts_idx": "true"},
                {"name": "k2", "type": "string", "add_ts_idx": "false"},
                {"name": "k3", "type": "string", "add_ts_idx": "false"},
            ],
        }
        utils.gen_table_meta_file(table_meta, metadata_path)
        rs0 = self.ns_create(self.ns_leader, metadata_path)
        self.assertIn('Create table ok', rs0)
        self.multidimension_vk = {'k1': ('string:index', 'testvalue0'),
                                  'k2': ('string', 'testvalue0'),
                                  'k3': ('string', 'testvalue0')}
        self.multidimension_scan_vk = {'k1': 'testvalue0'}

        rs1 = self.showtable(self.ns_leader, name)
        tid = rs1.keys()[0][1]

        rs = self.disconnectzk(self.leader)
        self.assertIn('disconnect zk ok', rs)
        rs = self.updatetablealive(self.ns_leader, name, '*', self.leader, 'no')
        self.assertIn('update ok', rs)
        time.sleep(3)

        rs = self.changeleader(self.ns_leader, name, 0, 'auto')
        self.assertIn('change leader ok', rs)
        time.sleep(2)
        rs = self.connectzk(self.leader)
        self.assertIn('connect zk ok', rs)
        for repeat in range(20):
            time.sleep(2)
            rs = self.ns_showopstatus(self.ns_leader)
            tablestatus = self.parse_tb(rs, ' ', [0, 1, 2, 3], [4, 5, 6, 7])
            kDone_cnt = 0
            cnt = 0
            flag = False
            for status in tablestatus:
                if status[2] == name:
                    cnt = cnt + 1
                    infoLogger.info('{} =  {}'.format(status, tablestatus[status]))
                    if tablestatus[status][0] == 'kFailed':
                        infoLogger.error('{} =  {}'.format(status, tablestatus[status]))
                        flag = True
                        break
                    if tablestatus[status][0] == 'kDone':
                        infoLogger.info('{} =  {}'.format(status, tablestatus[status]))
                        kDone_cnt = kDone_cnt + 1
            if flag == True:
                break
            if kDone_cnt == cnt:
                break

        rs2 = self.showtable(self.ns_leader)
        act1 = rs2[(name, tid, '0', self.slave1)]
        act2 = rs2[(name, tid, '0', self.slave2)]
        roles = [x[0] for x in [act1, act2]]
        for repeat in range(20):
            rs = self.showtable(self.ns_leader, name)
            act1 = rs2[(name, tid, '0', self.slave1)]
            act2 = rs2[(name, tid, '0', self.slave2)]
            roles = [x[0] for x in [act1, act2]]
            if roles.count('leader') == 1 and roles.count('follower') == 1:
                self.assertEqual(roles.count('leader'), 1)
                self.assertEqual(roles.count('follower'), 1)
                break
            time.sleep(2)
        self.assertEqual(rs2[(name, tid, '0', self.leader)], ['leader', '144000min', 'no', 'kNoCompress'])
        self.assertEqual(rs2[(name, tid, '1', self.leader)], ['leader', '144000min', 'no', 'kNoCompress'])
        self.assertEqual(rs2[(name, tid, '2', self.leader)], ['leader', '144000min', 'no', 'kNoCompress'])
        if roles.count('leader') != 1:
            rs = self.ns_showopstatus(self.ns_leader)
            infoLogger.debug(rs)
            self.assertEqual(roles.count('leader'), 1)
        self.assertEqual(roles.count('leader'), 1)
        self.assertEqual(roles.count('follower'), 1)

        leader_new = self.slave1 if 'leader' in act1 else self.slave2
        follower = self.slave1 if 'follower' in act1 else self.slave2
        rs2 = self.put(self.leader, tid, 1, 'testkey0', self.now(), 'testvalue0')
        self.assertIn('Put ok', rs2)
        rs3 = self.put(self.slave1, tid, 1, 'testkey0', self.now(), 'testvalue0')
        self.assertIn('Put failed', rs3)
        rs4 = self.put(leader_new, tid, 0, 'testkey0', self.now(), 'testvalue0')
        self.assertIn('Put ok', rs4)
        time.sleep(1)
        self.assertIn('testvalue0', self.scan(follower, tid, 0, 'testkey0', self.now(), 1))
        self.ns_drop(self.ns_leader, name)

    @ddt.data(
        ['kSSD'],
        ['kHDD'],
    )
    @ddt.unpack
    def test_changeleader_master_killed(self,storage_mode):
        """
        changeleader功能正常，主节点挂掉后，可以手工故障切换，切换成功后从节点可以同步数据
        原主节点启动后可以手工recoversnapshot成功
        :return:
        """
        self.start_client(self.leader)
        metadata_path = '{}/metadata.txt'.format(self.testpath)
        name = 'tname{}'.format(time.time())
        table_meta = {
            "name": name,
            "ttl": 144000,
            "storage_mode": storage_mode,
            "table_partition": [
                {"endpoint": self.leader,"pid_group": "0-2","is_leader": "true"},
                {"endpoint": self.slave1,"pid_group": "0-1","is_leader": "false"},
                {"endpoint": self.slave2,"pid_group": "0-1","is_leader": "false"},
            ],
            "column_desc":[
                {"name": "k1", "type": "string", "add_ts_idx": "true"},
                {"name": "k2", "type": "string", "add_ts_idx": "false"},
                {"name": "k3", "type": "string", "add_ts_idx": "false"},
            ],
        }
        utils.gen_table_meta_file(table_meta, metadata_path)
        rs0 = self.ns_create(self.ns_leader, metadata_path)
        self.assertIn('Create table ok', rs0)
        self.multidimension_vk = {'k1': ('string:index', 'testvalue0'),
                                  'k2': ('string', 'testvalue0'),
                                  'k3': ('string', 'testvalue0')}
        self.multidimension_scan_vk = {'k1': 'testvalue0'}

        rs1 = self.showtable(self.ns_leader, name)
        tid = rs1.keys()[0][1]

        self.stop_client(self.leader)
        self.updatetablealive(self.ns_leader, name, '*', self.leader, 'no')
        time.sleep(5)

        self.changeleader(self.ns_leader, name, 0)
        time.sleep(5)
        rs2 = self.showtable(self.ns_leader)
        self.start_client(self.leader)
        time.sleep(1)
        self.assertEqual(rs2[(name, tid, '0', self.leader)], ['leader', '144000min', 'no', 'kNoCompress'])
        self.assertEqual(rs2[(name, tid, '1', self.leader)], ['leader', '144000min', 'no', 'kNoCompress'])
        self.assertEqual(rs2[(name, tid, '2', self.leader)], ['leader', '144000min', 'no', 'kNoCompress'])
        act1 = rs2[(name, tid, '0', self.slave1)]
        act2 = rs2[(name, tid, '0', self.slave2)]
        roles = [x[0] for x in [act1, act2]]
        self.assertEqual(roles.count('leader'), 1)
        self.assertEqual(roles.count('follower'), 1)

        leader_new = self.slave1 if 'leader' in act1 else self.slave2
        follower = self.slave1 if 'follower' in act1 else self.slave2
        rs2 = self.put(self.leader, tid, 1, 'testkey0', self.now(), 'testvalue0')
        rs3 = self.put(self.slave1, tid, 1, 'testkey0', self.now(), 'testvalue0')
        rs4 = self.put(leader_new, tid, 0, 'testkey0', self.now(), 'testvalue0')
        self.assertFalse('Put ok' in rs2)
        self.assertFalse('Put ok' in rs3)
        self.assertIn('Put ok', rs4)
        time.sleep(1)
        self.assertIn('testvalue0', self.scan(follower, tid, 0, 'testkey0', self.now(), 1))
        self.ns_drop(self.ns_leader, name)

    @ddt.data(
        ['kSSD'],
        ['kHDD'],
    )
    @ddt.unpack
    def test_changeleader_master_alive(self,storage_mode):
        """
        changeleader传入有主节点的表，执行失败. 加上auto参数可以执行成功
        :return:
        """
        metadata_path = '{}/metadata.txt'.format(self.testpath)
        name = 'tname{}'.format(time.time())
        # m = utils.gen_table_metadata(
        #     '"{}"'.format(name), None, 144000, 2,
        #     ('table_partition', '"{}"'.format(self.leader), '"0-2"', 'true'),
        #     ('table_partition', '"{}"'.format(self.slave1), '"0-1"', 'false'),
        # )
        # utils.gen_table_metadata_file(m, metadata_path)

        table_meta = {
            "name": name,
            "ttl": 144000,
            "storage_mode": storage_mode,
            "table_partition": [
                {"endpoint": self.leader,"pid_group": "0-2","is_leader": "true"},
                {"endpoint": self.slave1,"pid_group": "0-1","is_leader": "false"},
            ],
        }
        utils.gen_table_meta_file(table_meta, metadata_path)
        rs1 = self.ns_create(self.ns_leader, metadata_path)
        self.assertIn('Create table ok', rs1)

        rs2 = self.changeleader(self.ns_leader, name, 0)
        self.assertIn('failed to change leader', rs2)
        rs3 = self.changeleader(self.ns_leader, name, 0, 'auto')
        self.assertIn('change leader ok', rs3)
        time.sleep(3)
        self.ns_drop(self.ns_leader, name)
    @ddt.data(
        ['kSSD'],
        ['kHDD'],
    )
    @ddt.unpack
    def test_changeleader_candidate_leader(self,storage_mode):
        """
        指定candidate_leader
        :return:
        """
        self.get_new_ns_leader()
        metadata_path = '{}/metadata.txt'.format(self.testpath)
        name = 'tname{}'.format(time.time())
        # m = utils.gen_table_metadata(
        #     '"{}"'.format(name), None, 144000, 2,
        #     ('table_partition', '"{}"'.format(self.leader), '"0-2"', 'true'),
        #     ('table_partition', '"{}"'.format(self.slave1), '"0-1"', 'false'),
        #     ('table_partition', '"{}"'.format(self.slave2), '"0-1"', 'false'),
        #     ('column_desc', '"k1"', '"string"', 'true'),
        #     ('column_desc', '"k2"', '"string"', 'false'),
        #     ('column_desc', '"k3"', '"string"', 'false')
        # )
        # utils.gen_table_metadata_file(m, metadata_path)

        table_meta = {
            "name": name,
            "ttl": 144000,
            "storage_mode": storage_mode,
            "table_partition": [
                {"endpoint": self.leader,"pid_group": "0-2","is_leader": "true"},
                {"endpoint": self.slave1,"pid_group": "0-1","is_leader": "false"},
                {"endpoint": self.slave2,"pid_group": "0-1","is_leader": "false"},
            ],
            "column_desc":[
                {"name": "k1", "type": "string", "add_ts_idx": "true"},
                {"name": "k2", "type": "string", "add_ts_idx": "false"},
                {"name": "k3", "type": "string", "add_ts_idx": "false"},
            ],
        }
        utils.gen_table_meta_file(table_meta, metadata_path)
        rs1 = self.ns_create(self.ns_leader, metadata_path)
        self.assertIn('Create table ok', rs1)
        result = self.showtable(self.ns_leader)
        tid = result.keys()[0][1]
        rs2 = self.put(self.leader, tid, 0, 'testkey0', self.now(), 'testvalue0')
        self.assertIn('Put ok', rs2)

        rs3 = self.changeleader(self.ns_leader, name, 0, self.slave1)
        self.assertIn('change leader ok', rs3)
        time.sleep(3)
        rs4 = self.showtable(self.ns_leader)
        self.assertEqual(rs4[(name, tid, '0', self.leader)], ['leader', '144000min', 'no', 'kNoCompress'])
        self.assertEqual(rs4[(name, tid, '0', self.slave1)], ['leader', '144000min', 'yes', 'kNoCompress'])
        self.assertEqual(rs4[(name, tid, '0', self.slave2)], ['follower', '144000min', 'yes', 'kNoCompress'])

        rs5 = self.put(self.slave1, tid, 0, 'testkey1', self.now(), 'testvalue1')
        self.assertIn('Put ok', rs5)
        time.sleep(1)
        self.multidimension_scan_vk = {'k1': 'testvalue1'}
        self.assertIn('testvalue1', self.scan(self.slave2, tid, 0, 'testkey1', self.now(), 1))
        self.ns_drop(self.ns_leader, name)

    @ddt.data(
        (0, 'auto', 'no','kSSD'),
        (1, 'auto', 'no','kSSD'),
        (0, 'auto', 'no','kHDD'),
        (1, 'auto', 'no','kHDD'),
    )
    @ddt.unpack
    def test_changeleader_auto_without_offline(self, pid, switch,rsp_msg,storage_mode):
        """
        不当机更新leader, auto模式（1 leader 2 follower)。在三个副本的情况下，进行changeleader 参数是auto，测试自动切换是否成功
        :return:
        """
        metadata_path = '{}/metadata.txt'.format(self.testpath)
        name = 'tname{}'.format(time.time())
        # m = utils.gen_table_metadata(
        #     '"{}"'.format(name), None, 144000, 2,
        #     ('table_partition', '"{}"'.format(self.leader), '"0-2"', 'true'),
        #     ('table_partition', '"{}"'.format(self.slave1), '"0-1"', 'false'),
        #     ('table_partition', '"{}"'.format(self.slave2), '"0-1"', 'false'),
        #     ('column_desc', '"k1"', '"string"', 'true'),
        #     ('column_desc', '"k2"', '"string"', 'false'),
        #     ('column_desc', '"k3"', '"string"', 'false')
        # )
        # utils.gen_table_metadata_file(m, metadata_path)

        table_meta = {
            "name": name,
            "ttl": 144000,
            "storage_mode": storage_mode,
            "table_partition": [
                {"endpoint": self.leader,"pid_group": "0-2","is_leader": "true"},
                {"endpoint": self.slave1,"pid_group": "0-1","is_leader": "false"},
                {"endpoint": self.slave2,"pid_group": "0-1","is_leader": "false"},
            ],
            "column_desc":[
                {"name": "k1", "type": "string", "add_ts_idx": "true"},
                {"name": "k2", "type": "string", "add_ts_idx": "false"},
                {"name": "k3", "type": "string", "add_ts_idx": "false"},
            ],
        }
        utils.gen_table_meta_file(table_meta, metadata_path)
        rs0 = self.ns_create(self.ns_leader, metadata_path)
        self.assertIn('Create table ok', rs0)
        self.multidimension_vk = {'k1': ('string:index', 'testvalue0'),
                                  'k2': ('string', 'testvalue0'),
                                  'k3': ('string', 'testvalue0')}
        self.multidimension_scan_vk = {'k1': 'testvalue0'}

        rs1 = self.showtable(self.ns_leader)
        tid = rs1.keys()[0][1]

        self.assertEqual(rs1[(name, tid,  str(pid), self.leader)], ['leader', '144000min', 'yes', 'kNoCompress'])
        self.assertEqual(rs1[(name, tid,  str(pid), self.slave1)], ['follower', '144000min', 'yes', 'kNoCompress'])
        self.assertEqual(rs1[(name, tid,  str(pid), self.slave2)], ['follower', '144000min', 'yes', 'kNoCompress'])

        self.changeleader(self.ns_leader, name, pid, switch)
        time.sleep(1)

        rs2 = self.showtable(self.ns_leader)
        self.assertEqual(rs2[(name, tid,  str(pid), self.leader)], ['leader', '144000min', rsp_msg, 'kNoCompress'])
        flag = 'false'
        if (rs2[(name, tid,  str(pid), self.slave1)] == ['leader', '144000min', 'yes', 'kNoCompress'] and
            rs2[(name, tid,  str(pid), self.slave2)] == ['follower', '144000min', 'yes', 'kNoCompress']):
            flag = 'true'
        if (rs2[(name, tid,  str(pid), self.slave1)] == ['follower', '144000min', 'yes', 'kNoCompress'] and
            rs2[(name, tid,  str(pid), self.slave2)] == ['leader', '144000min', 'yes', 'kNoCompress']):
            flag = 'true'
        self.assertEqual(flag, 'true')
        self.ns_drop(self.ns_leader, name)

    @ddt.data(
        (0, conf.tb_endpoints[1], conf.tb_endpoints[2], 'no','kSSD'),
        (1, conf.tb_endpoints[1], conf.tb_endpoints[2], 'no','kSSD'),
        (0, conf.tb_endpoints[1], conf.tb_endpoints[2], 'no','kHDD'),
        (1, conf.tb_endpoints[1], conf.tb_endpoints[2], 'no','kHDD'),
    )
    @ddt.unpack
    def test_changeleader_with_many_times(self, pid, switch, switch1, rsp_msg,storage_mode):
        """
        不当机更新leader,多次changeleader。有follower情况，change成功，无follow情况，change失败
        :return:
        """
        metadata_path = '{}/metadata.txt'.format(self.testpath)
        name = 'tname{}'.format(time.time())
        table_meta = {
            "name": name,
            "ttl": 144000,
            "storage_mode": storage_mode,
            "table_partition": [
                {"endpoint": self.leader,"pid_group": "0-2","is_leader": "true"},
                {"endpoint": self.slave1,"pid_group": "0-1","is_leader": "false"},
                {"endpoint": self.slave2,"pid_group": "0-1","is_leader": "false"},
            ],
            "column_desc":[
                {"name": "k1", "type": "string", "add_ts_idx": "true"},
                {"name": "k2", "type": "string", "add_ts_idx": "false"},
                {"name": "k3", "type": "string", "add_ts_idx": "false"},
            ],
        }
        utils.gen_table_meta_file(table_meta, metadata_path)
        rs0 = self.ns_create(self.ns_leader, metadata_path)
        self.assertIn('Create table ok', rs0)
        self.multidimension_vk = {'k1': ('string:index', 'testvalue0'),
                                  'k2': ('string', 'testvalue0'),
                                  'k3': ('string', 'testvalue0')}
        self.multidimension_scan_vk = {'k1': 'testvalue0'}

        rs1 = self.showtable(self.ns_leader)
        tid = rs1.keys()[0][1]

        self.assertEqual(rs1[(name, tid,  str(pid), self.leader)], ['leader', '144000min', 'yes', 'kNoCompress'])
        self.assertEqual(rs1[(name, tid,  str(pid), self.slave1)], ['follower', '144000min', 'yes', 'kNoCompress'])
        self.assertEqual(rs1[(name, tid,  str(pid), self.slave2)], ['follower', '144000min', 'yes', 'kNoCompress'])

        rs_change1 = self.changeleader(self.ns_leader, name, pid, switch)
        time.sleep(1)
        self.assertTrue('change leader ok' in rs_change1)
        rs_change2 = self.changeleader(self.ns_leader, name, pid, switch1)
        time.sleep(1)
        self.assertTrue('change leader ok' in rs_change2)
        rs_change3 = self.changeleader(self.ns_leader, name, pid, 'auto')
        self.assertTrue('failed to change leader. error msg: no alive follower' in rs_change3)
        rs_change4 = self.changeleader(self.ns_leader, name, pid, 'auto')
        self.assertTrue('failed to change leader. error msg: no alive follower' in rs_change4)
        rs_change5 = self.changeleader(self.ns_leader, name, pid, switch)
        self.assertTrue('failed to change leader. error msg: no alive follower' in rs_change5)
        rs_change6 = self.changeleader(self.ns_leader, name, pid, self.leader)
        self.assertTrue('failed to change leader. error msg: no alive follower' in rs_change6)
        self.ns_drop(self.ns_leader, name)

if __name__ == "__main__":
    load(TestChangeLeader)
