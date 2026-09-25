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
    def test_variant_review_flow(self):
        self.db.grant_work_access(self.work,self.reviewer,"review",self.owner)
        self.db.grant_work_access(self.work,self.editor,"review",self.owner)
        variant=self.db.create_variant(self.passage,self.w2,"春水东流，故人南去。","按语义补足",self.editor,0)
        with self.assertRaisesRegex(DomainError,"approved 或 rejected"):
            self.db.review_variant(variant,"maybe","意见充分",self.reviewer,1)
        with self.assertRaisesRegex(DomainError,"意见"):
            self.db.review_variant(variant,"approved","",self.reviewer,1)
        with self.assertRaisesRegex(DomainError,"审阅权限"):
            self.db.review_variant(variant,"approved","同意补足",self.outsider,1)
        with self.assertRaisesRegex(DomainError,"自己创建"):
            self.db.review_variant(variant,"approved","同意补足",self.editor,1)
        with self.assertRaisesRegex(DomainError,"内容已更新"):
            self.db.review_variant(variant,"approved","同意补足",self.reviewer,0)
        review=self.db.review_variant(variant,"approved","同意补足",self.reviewer,1)
        self.assertEqual("approved",review["status"]); self.assertEqual("审阅",review["reviewer_name"]); self.assertFalse(review["stale"])
        review=self.db.review_variant(variant,"rejected","补字证据不足",self.reviewer,1)
        self.assertEqual("rejected",review["status"])
        self.assertEqual(1,self.db.conn.execute("SELECT COUNT(*) FROM variant_reviews WHERE variant_id=?",(variant,)).fetchone()[0])
        exported=self.db.export_collation(self.work,self.owner)
        r=exported["passages"][0]["variants"][0]["review"]
        self.assertEqual("rejected",r["status"]); self.assertEqual("补字证据不足",r["comment"]); self.assertEqual("审阅",r["reviewer_name"])
        self.db.update_variant(variant,"春水东流，[不可辨]人南去。","墨迹受损，谨慎处理",self.editor,1)
        r=self.db.export_collation(self.work,self.owner)["passages"][0]["variants"][0]["review"]
        self.assertEqual("pending",r["status"]); self.assertTrue(r["stale"]); self.assertEqual("审阅",r["reviewer_name"])
        own=self.db.create_variant(self.passage,self.w1,"春水东流，故人南去。","负责人自校",self.owner,2)
        review=self.db.review_variant(own,"approved","负责人复核通过",self.owner,3)
        self.assertEqual("approved",review["status"])

if __name__=="__main__": unittest.main()
