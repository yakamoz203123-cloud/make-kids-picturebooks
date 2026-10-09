import hashlib,json,sys,tempfile,unittest,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
class PackageTests(unittest.TestCase):
 def test_rejects_output_outside_project(self):
  from package_project import package_project
  with tempfile.TemporaryDirectory() as td:
   workspace=Path(td);root=workspace/'project';root.mkdir();(root/'story.md').write_text('saved',encoding='utf-8')
   receipt={'schema_version':1,'book_id':'b1','age_band':'3-4','source_version':'v1','characters_version':'v1','files':{'story.md':hashlib.sha256((root/'story.md').read_bytes()).hexdigest()}}
   (root/'receipt.json').write_text(json.dumps(receipt),encoding='utf-8')
   project={'source':{'version':'v1'},'characters_version':'v1','books':[{'id':'b1','age_band':'3-4','artifacts':{'story':'story.md','acceptance':'receipt.json'}}]}
   project_path=root/'project.json';project_path.write_text(json.dumps(project),encoding='utf-8')
   output=workspace/'outside.zip'
   with self.assertRaises(ValueError):package_project(project_path,'b1',output)
   self.assertFalse(output.exists())
 def test_package_current_assets_only_and_refuse_stale(self):
  from package_project import package_project
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);(root/'assets').mkdir();(root/'assets'/'story.md').write_text('saved',encoding='utf-8');(root/'old.png').write_text('unused',encoding='utf-8')
   receipt={'schema_version':1,'book_id':'b1','age_band':'3-4','source_version':'v1','characters_version':'v1','files':{'assets\\story.md':hashlib.sha256((root/'assets'/'story.md').read_bytes()).hexdigest()}}
   (root/'receipt.json').write_text(json.dumps(receipt),encoding='utf-8')
   project={'source':{'version':'v1'},'characters_version':'v1','books':[{'id':'b1','age_band':'3-4','artifacts':{'story':'assets\\story.md','acceptance':'receipt.json'}}]}
   p=root/'project.json';p.write_text(json.dumps(project),encoding='utf-8')
   package_project(p,'b1',root/'one.zip')
   with zipfile.ZipFile(root/'one.zip') as z:
    self.assertEqual(set(z.namelist()),{'project.json','receipt.json','assets/story.md'})
    self.assertTrue(all('\\' not in name for name in z.namelist()))
   with self.assertRaises(FileExistsError):package_project(p,'b1',root/'one.zip')
   (root/'assets'/'story.md').write_text('modified',encoding='utf-8')
   with self.assertRaises(ValueError):package_project(p,'b1',root/'two.zip')
   self.assertFalse((root/'two.zip').exists())
if __name__=='__main__':unittest.main()
