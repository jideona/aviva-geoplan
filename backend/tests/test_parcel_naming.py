from app.domain.parcels import clean_name, looks_unnamed


def test_placeholder_names_are_detected():
    assert looks_unnamed("Unnamed Est Wuye")
    assert looks_unnamed("")
    assert looks_unnamed("??")


def test_question_marks_inside_a_bracketed_name_are_detected():
    name, code, _ = clean_name("GC-59 [?? Estate Wuye]")
    assert looks_unnamed(name, code)


def test_a_bare_survey_code_is_not_a_name():
    assert looks_unnamed("GC-70", "GC-70")


def test_real_estate_names_pass():
    assert not looks_unnamed("Ivy Apartments Estate Wuye")
    assert not looks_unnamed("Crownet Plaza")
    assert not looks_unnamed("Yah Wahab Estate Phase2")
    assert not looks_unnamed("Brains & Hammers Estate Wuye")


def test_a_descriptive_name_is_still_a_name():
    # A surveyor's description locates the estate even without its formal name.
    assert not looks_unnamed("Beside Highgate Apartments")
    assert not looks_unnamed("3 Terraces")
