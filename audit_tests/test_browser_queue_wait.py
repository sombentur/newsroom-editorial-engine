import sys
from pathlib import Path
from unittest import IsolatedAsyncioTestCase
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
class BrowserQueueTests(IsolatedAsyncioTestCase):
 async def test_queue_wait_does_not_consume_generation_timeout(self):
  from lib import browser_bridge as b
  job={'id':'test','status':'queued','prompt':'prompt'}
  with patch.object(b,'db',SimpleNamespace(browser_jobs=SimpleNamespace(update_one=AsyncMock(),find_one=AsyncMock(side_effect=[job,{'result':'image-result'}])))), patch.object(b,'job_status',AsyncMock(side_effect=[{'status':'queued'},{'status':'queued'},{'status':'running'},{'status':'completed'}])), patch.object(b.asyncio,'sleep',AsyncMock()),patch.object(b,'unavailable_reason',AsyncMock(return_value=None)),patch.object(b.time,'monotonic',return_value=99999) as clock:
   self.assertEqual(await b.run_job('image','article','prompt',120),'image-result')
   self.assertEqual(clock.call_count,1)
 async def test_disconnected_work_tab_holds_instead_of_waiting_forever(self):
  from lib import browser_bridge as b
  from lib.ai import AIError
  job={'id':'test','status':'queued','prompt':'prompt'}
  with patch.object(b,'db',SimpleNamespace(browser_jobs=SimpleNamespace(update_one=AsyncMock(),find_one=AsyncMock(return_value=job)))), patch.object(b,'job_status',AsyncMock(return_value={'status':'queued'})), patch.object(b.asyncio,'sleep',AsyncMock()),patch.object(b,'unavailable_reason',AsyncMock(return_value='The Gemini research work tab is not connected')),patch.object(b.time,'monotonic',side_effect=[0,100,b.UNAVAILABLE_GRACE]):
   with self.assertRaisesRegex(AIError,'not connected.*stays queued'):
    await b.run_job('research','article','prompt',3600)
 async def test_busy_but_connected_extension_keeps_waiting(self):
  from lib import browser_bridge as b
  job={'id':'test','status':'queued','prompt':'prompt'}
  with patch.object(b,'db',SimpleNamespace(browser_jobs=SimpleNamespace(update_one=AsyncMock(),find_one=AsyncMock(side_effect=[job,{'result':'report'}])))), patch.object(b,'job_status',AsyncMock(side_effect=[{'status':'queued'}]*50+[{'status':'completed'}])), patch.object(b.asyncio,'sleep',AsyncMock()),patch.object(b,'unavailable_reason',AsyncMock(return_value=None)):
   self.assertEqual(await b.run_job('research','article','prompt',3600),'report')
 def test_extra_english_thumbnail_line_is_trimmed(self):
  from lib.thumbnails import validate_headlines
  self.assertEqual(validate_headlines(['One','Two','Three'],'en'),['One','Two'])
  with self.assertRaises(ValueError):
   validate_headlines(['Only one'],'en')
