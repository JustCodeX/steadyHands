from trainer.audio.lines import all_lines, number_id
from trainer.audio.phrase_builder import PhraseBuilder
from trainer.core.events import RoundResult


def test_result_phrase_uses_existing_line_ids():
    lines = all_lines()
    r = RoundResult(level_name="L", won=True, time_s=48.3, contacts=2, steadiness=85.0, calls_correct=3, calls_wrong=0, steady_uses=1)
    ids = PhraseBuilder.result(r)
    assert ids[:3] == ["win", number_id(48), "seconds"]
    assert all(i in lines for i in ids)


def test_event_phrases_exist():
    lines = all_lines()
    for kind in ("hit", "item_out", "clamped", "pardon", "wrong_tool", "bleed_timeout", "win", "lose"):
        for i in PhraseBuilder.for_event(kind, "", 0):
            assert i in lines
    assert PhraseBuilder.for_event("tool_changed", "clamp", 0) == ["clamp"]
    assert PhraseBuilder.for_event("help", "forceps,steady", 0) == ["you_can_say", "forceps", "steady"]


# --- the nurse at the vitals monitor ------------------------------------------------


def test_nurse_alarm_reminder_and_read_back_with_the_amount():
    from trainer.audio.lines import NURSE_LINES, all_lines, line_text

    pb = PhraseBuilder()
    assert pb.for_event("vital_alarm", "spo2:91", 0) == ["alarm_spo2"]
    assert pb.for_event("vital_over", "bis:27", 0) == ["over_bis"]
    assert pb.for_event("vital_reminder", "bp:84", 0) == ["remind_bp", "nn_84", "unit_bp"]  # numbers in her voice
    assert pb.for_event("vital_still", "bis:63", 0) == ["still_bis", "nn_63"]  # BIS has no unit
    assert pb.for_event("treatment", "propofol:correct:bis:30:", 0) == ["give_propofol", "nn_30", "unit_mg"]
    assert pb.for_event("treatment", "adrenaline:partial:bp:10:standard", 0) == ["standard_dose", "give_adrenaline", "nn_10", "unit_mcg"]
    assert pb.for_event("treatment", "adrenaline:wrong:spo2:10:", 0)[-1] == "not_helped"
    assert pb.for_event("treatment", "propofol:unneeded::20:", 0)[-1] == "unneeded"
    assert pb.for_event("treatment", "propofol:overdose:bis:90:", 0)[-1] == "overdose"
    assert pb.for_event("treatment", "oxygen:overdose:spo2:100:", 0) == ["give_oxygen", "nn_100", "unit_percent", "too_much_oxygen"]
    assert pb.for_event("treatment", "oxygen:already:spo2:60:", 0) == ["already"]
    assert pb.for_event("treatment", "propofol:correct:bis:200:", 0)[1] == "nn_200"  # the largest dose has its clip
    assert pb.for_event("vital_crisis", "bis:77", 0) == ["crisis"]
    assert line_text(["remind_spo2", "nn_88", "unit_percent"]) == "Saturation is at 88 percent."
    assert line_text(["standard_dose", "give_propofol", "nn_30", "unit_mg"]) == "Standard dose. Propofol 30 milligrams."
    every = all_lines()
    for kind, detail in [
        ("vital_alarm", "bis:63"), ("vital_over", "bp:165"), ("vital_reminder", "spo2:89"), ("vital_still", "bp:84"),
        ("vital_stable", "bp:120"), ("pardon_doctor", ""), ("you_can_order", ""),
        ("treatment", "oxygen:partial:spo2:50:standard"), ("treatment", "adrenaline:overdose:bp:40:"),
    ]:
        assert all(i in every for i in pb.for_event(kind, detail, 0)), kind
    assert all(len(NURSE_LINES[f"{side}_{k}"].split()) <= 6 for side, k in [("alarm", "spo2"), ("alarm", "bis"), ("alarm", "bp"), ("over", "bis"), ("over", "bp")])


def test_result_names_the_instructions_and_crises():
    base = dict(level_name="x", won=True, time_s=40, contacts=0, steadiness=80, calls_correct=0, calls_wrong=0, steady_uses=0)
    ids = PhraseBuilder.result(RoundResult(**base, treatments_correct=2, treatments_wrong=0, crises=0))
    assert "treat_good" in ids and "crises_one" not in ids
    ids = PhraseBuilder.result(RoundResult(**base, treatments_correct=1, treatments_wrong=1, overdoses=1, crises=2))
    assert "treat_wrong" in ids and ids[-2:] == ["n_2", "crises"]


def test_nurse_lines_come_with_a_subtitle_and_alarms_interrupt():
    from trainer.audio.sound_service import URGENT, SoundService
    from trainer.core.config import AudioConfig
    from trainer.core.event_bus import EventBus
    from trainer.core.events import GameEvent, Subtitle

    bus = EventBus()
    seen = []
    bus.subscribe(Subtitle, seen.append)
    SoundService(bus, AudioConfig(enabled=False))
    bus.publish(GameEvent(kind="vital_reminder", detail="spo2:87"))
    bus.publish(GameEvent(kind="hit"))
    bus.dispatch()
    assert [(s.speaker, s.text) for s in seen] == [("nurse", "Saturation is at 87 percent.")]
    assert {"vital_alarm", "vital_reminder", "vital_crisis"} <= URGENT


def test_keys_5_to_7_give_the_treatments():
    from trainer.core.event_bus import EventBus
    from trainer.core.events import CommandEvent, KeyEvent
    from trainer.hardware.keyboard_input import KeyboardInput

    bus = EventBus()
    seen = []
    bus.subscribe(CommandEvent, seen.append)
    KeyboardInput(bus)
    for key in "567":
        bus.publish(KeyEvent(key=key, down=True))
    bus.dispatch()
    assert [(c.word, c.amount) for c in seen] == [("oxygen", None), ("propofol", None), ("adrenaline", None)]  # standard doses


def test_the_nurse_has_her_own_voice_when_its_file_is_there(tmp_path):
    from trainer.audio.lines import nurse_ids
    from trainer.audio.tts_renderer import TtsRenderer

    patient, nurse = tmp_path / "patient.onnx", tmp_path / "nurse.onnx"
    patient.write_bytes(b"x")
    nurse.write_bytes(b"x")
    rendered = []
    r = TtsRenderer(tmp_path / "clips", "piper", patient, nurse_voice=nurse)
    r.render = lambda text, out, voice=None: (rendered.append((out.stem, voice)), out.write_bytes(b"w"))
    assert r.render_all() > 0
    voices = dict(rendered)
    assert voices["alarm_spo2"] == nurse and voices["nn_88"] == nurse
    assert voices["ouch_1"] == patient and voices["n_88"] == patient
    rendered.clear()
    assert r.render_all(force_nurse=True) == len(nurse_ids())  # only hers again
    no_file = TtsRenderer(tmp_path / "clips", "piper", patient, nurse_voice=tmp_path / "missing.onnx")
    assert no_file.voice_for("alarm_spo2") == patient
