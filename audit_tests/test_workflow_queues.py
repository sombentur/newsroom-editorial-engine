import asyncio
import sys
from pathlib import Path
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
class QueueTests(IsolatedAsyncioTestCase):
 async def test_approved_writing_does_not_wait_for_research(self):
  from routers import pipeline as p
  art={'id':'fixture','site_key':'human','stage':'research_validated','dossier':{'summary':'ready'},'validation':{'passed':True}}
  done={**art,'article':{'headline':'done'},'quality_gate':{'passed':True},'image':{'ready':True},'stage':'image_ready'}
  with patch.object(p,'_workflow_slots',asyncio.Semaphore(0)), patch.object(p,'_writing_slots',asyncio.Semaphore(1)), patch.object(p,'_article_or_404',AsyncMock(return_value=art)), patch.object(p,'_site_or_404',AsyncMock(return_value={})), patch.object(p,'run_article_stage',AsyncMock(return_value=done)) as writing, patch.object(p,'run_research_stage',AsyncMock()) as research, patch('lib.turn.wait_for_turn',AsyncMock(return_value=True)):
   await asyncio.wait_for(p._pipeline_in_background('fixture'),1)
   writing.assert_awaited_once();research.assert_not_awaited()
