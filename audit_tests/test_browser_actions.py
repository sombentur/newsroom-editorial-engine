import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from lib.browser_actions import initial_action
from lib.browser_controller import Observation, validate_decision


def obs(elements, **kwargs):
    return Observation(snapshot='s',url='https://gemini.google.com/app',text='',elements=elements,**kwargs)


def button(i,name,role='button',**kwargs):
    return dict(id=i,role=role,name=name,**kwargs)


def test_research_enables_tool_before_prompt_or_send():
    page=obs([button(1,'Open mode picker, currently Pro'),button(2,'Upload & tools'),button(3,'Send message')],filled=True,prompt_verified=True)
    result=initial_action({'kind':'research'},page)
    assert (result.action,result.target)==('click',2)
    validate_decision({'kind':'research'},page,result)


def test_tools_menu_sequence():
    picker=button(1,'Open mode picker, currently Pro')
    for controls, expected in [([button(2,'More tools')],2),([button(3,'Deep research','menuitemcheckbox')],3)]:
        result=initial_action({'kind':'research'},obs([picker,*controls]))
        assert (result.action,result.target)==('click',expected)


def test_select_pro_from_observed_menu():
    page=obs([button(1,'Open mode picker, currently Fast'),button(2,'3.1 Pro\nAdvanced reasoning','menuitem')])
    assert initial_action({'kind':'research'},page).target==2


def test_verified_research_uses_protected_submit():
    page=obs([button(1,'Open mode picker, currently Pro'),button(2,'Deselect Deep research'),button(3,'Send message')],filled=True,prompt_verified=True)
    result=initial_action({'kind':'research'},page)
    assert (result.action,result.target)==('submit',3)
    validate_decision({'kind':'research'},page,result)


def test_named_composer_avoids_gemini_nested_unnamed_field():
    page=obs([button(1,'Open mode picker, currently Pro'),button(2,'Deselect Deep research'),
        button(3,'Enter a prompt for Gemini','textbox',editable=True),button(4,'','textbox',editable=True)])
    result=initial_action({'kind':'research'},page)
    assert (result.action,result.target)==('fill_prompt',3)


def test_submitted_jobs_and_unknown_controls_fall_back():
    assert initial_action({'kind':'image'},obs([],submitted=True)) is None
    assert initial_action({'kind':'image','activity':[{'action':'submit'}]},obs([])) is None
    assert initial_action({'kind':'research'},obs([])) is None


def test_restored_draft_and_ambiguous_send_are_preserved():
    assert initial_action({'kind':'image'},obs([button(1,'Chat with ChatGPT','textbox',editable=True,empty=False)])) is None
    assert initial_action({'kind':'image'},obs([button(1,'Send prompt'),button(2,'Send prompt')],prompt_verified=True)) is None


def test_image_fills_then_submits():
    page=obs([button(1,'Chat with ChatGPT','textbox',editable=True),button(2,'Send prompt')])
    assert initial_action({'kind':'image'},page).action=='fill_prompt'
    page.prompt_verified=True
    assert initial_action({'kind':'image'},page).action=='submit'
