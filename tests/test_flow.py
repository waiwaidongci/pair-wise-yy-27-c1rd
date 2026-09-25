import os, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from database import CollationDB, DomainError

class CollationFlowTest(unittest.TestCase):
    def setUp(self):
        fd,self.path=tempfile.mkstemp(suffix=".db"); os.close(fd); self.db=CollationDB(self.path)
        self.owner=self.db.add_user("负责人","owner"); self.editor=self.db.add_user("编辑","editor"); self.reviewer=self.db.add_user("审阅","reviewer"); self.outsider=self.db.add_user("外部","reviewer")
        self.work=self.db.create_work("残卷","异文比较",self.owner)
        self.w1=self.db.add_witness(self.work,"甲本","version"); self.w2=self.db.add_witness(self.work,"乙本","fragment","馆藏残片","中段缺页")
        self.db.grant_witness_editor(self.w2,self.editor,self.owner); self.db.grant_work_access(self.work,self.reviewer,"view",self.owner)
        self.passage=self.db.add_passage(self.work,"第一节","春水东流，故人南去。",self.owner)
        self.db.align_passage(self.passage,self.w1,"春水东流，故人南去。",1,self.owner)
        self.db.align_passage(self.passage,self.w2,"春水东流，[缺页]",2,self.editor)
    def tearDown(self): self.db.close(); os.unlink(self.path)
    def test_multilayer_revision_snapshot_export_and_lock(self):
        variant=self.db.create_variant(self.passage,self.w2,"春水东流，故人南去。","按语义补足",self.editor,0)
        rev=self.db.update_variant(variant,"春水东流，[不可辨]人南去。","墨迹受损，不再直接补写",self.editor,1)
        self.assertEqual(2,rev)
        snap=self.db.get_snapshot(self.passage,2,self.owner)
        self.assertEqual(2,snap["layer"])
        exported=self.db.export_collation(self.work,self.reviewer)
        self.assertEqual(1,exported["gap_count"])
        self.assertTrue(exported["passages"][0]["variants"][0]["notes"] == [])
        self.db.lock_passage(self.passage,self.owner,"定稿")
        with self.assertRaisesRegex(DomainError,"锁定"):
            self.db.update_variant(variant,"另一文本","无意义修改",self.editor,2)
    def test_optimistic_lock_permission_and_mark_validation(self):
        first=self.db.create_variant(self.passage,self.w2,"补足一","理由一",self.editor,0)
        with self.assertRaisesRegex(DomainError,"版本冲突"):
            self.db.create_variant(self.passage,self.w2,"补足二","理由二",self.editor,0)
        with self.assertRaisesRegex(DomainError,"无权"):
            self.db.create_variant(self.passage,self.w2,"补足三","理由三",self.reviewer,1)
        with self.assertRaisesRegex(DomainError,"无权"):
            self.db.export_collation(self.work,self.outsider)
        with self.assertRaisesRegex(DomainError,"括号"):
            self.db.align_passage(self.passage,self.w1,"文本[未闭合",9,self.owner)
    def test_variant_review_flow_and_export(self):
        self.db.grant_work_access(self.work,self.reviewer,"review",self.owner)
        variant=self.db.create_variant(self.passage,self.w2,"春水东流，故人南去。","按语义补足",self.editor,0)
        # 仅 view 权限不能审定；创建者自己不能审定
        self.db.grant_work_access(self.work,self.reviewer,"view",self.owner)
        with self.assertRaisesRegex(DomainError,"审定权限"):
            self.db.review_variant(variant,"approved","通过",self.reviewer,1)
        with self.assertRaisesRegex(DomainError,"自己创建"):
            self.db.review_variant(variant,"approved","自审",self.editor,1)
        # 提交必须带当前段落修订号，旧页面操作提示内容已更新
        self.db.grant_work_access(self.work,self.reviewer,"review",self.owner)
        with self.assertRaisesRegex(DomainError,"内容已更新"):
            self.db.review_variant(variant,"approved","旧页面",self.reviewer,0)
        review=self.db.review_variant(variant,"approved","补字稳妥，核准",self.reviewer,1)
        self.assertEqual("approved",review["status"]); self.assertEqual(self.reviewer,review["reviewer_id"])
        # 同一异文只保留最新结论
        review=self.db.review_variant(variant,"rejected","与底本不合，驳回",self.reviewer,1)
        self.assertEqual("rejected",review["status"])
        exported=self.db.export_collation(self.work,self.owner)
        v=exported["passages"][0]["variants"][0]
        self.assertEqual("rejected",v["review_status"])
        self.assertEqual("与底本不合，驳回",v["review"]["comment"]); self.assertEqual("审阅",v["review"]["reviewer_name"])
        # 异文产生新修订，原结论失效，重新等待审定
        self.db.update_variant(variant,"春水东流，[不可辨]人南去。","改存疑处理",self.editor,1)
        exported=self.db.export_collation(self.work,self.owner)
        v=exported["passages"][0]["variants"][0]
        self.assertEqual("pending",v["review_status"]); self.assertIsNone(v["review"])
        # 新修订后再次核准成功（当前段落修订号为2）
        review=self.db.review_variant(variant,"approved","存疑处理可从",self.reviewer,2)
        self.assertEqual("approved",review["status"])
    def test_owner_can_review_own_variant(self):
        variant=self.db.create_variant(self.passage,self.w2,"春水东流，故人南去。","按语义补足",self.editor,0)
        review=self.db.review_variant(variant,"approved","负责人终审",self.owner,1)
        self.assertEqual("approved",review["status"]); self.assertEqual(self.owner,review["reviewer_id"])
    def test_review_validation(self):
        self.db.grant_work_access(self.work,self.reviewer,"review",self.owner)
        variant=self.db.create_variant(self.passage,self.w2,"春水东流，故人南去。","按语义补足",self.editor,0)
        with self.assertRaisesRegex(DomainError,"approved 或 rejected"):
            self.db.review_variant(variant,"maybe","结论",self.reviewer,1)
        with self.assertRaisesRegex(DomainError,"意见不能为空"):
            self.db.review_variant(variant,"approved","  ",self.reviewer,1)
        with self.assertRaisesRegex(DomainError,"审定权限"):
            self.db.review_variant(variant,"approved","外部意见",self.outsider,1)

if __name__=="__main__": unittest.main()
