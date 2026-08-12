from app.domain.name_matching import is_possible, is_strong, similarity, tokens


def test_suffixes_and_initials_are_stripped():
    assert tokens("N Okonjo-Iweala Way") == ["okonjo", "iweala"]
    assert tokens("Ameh Ebute Street") == ["ameh", "ebute"]


def test_the_case_that_failed_in_the_field():
    # Recorded by the surveyor vs how OpenStreetMap spells it.
    assert is_strong(similarity("N Okonjo-Iweala Way", "Ngozi Okonjo-Iweala"))


def test_abbreviated_and_full_forms_match():
    assert is_strong(similarity("Anyim Plus Anyim St", "Anyim Pius Anyim Street"))
    assert is_strong(similarity("Dimeji Bankole St", "Dimeji Bankole Street"))
    assert is_strong(similarity("Chinyeaka Ohaa Cres", "Chinyeaka Ohaa Crescent"))


def test_shared_road_type_alone_is_not_similarity():
    # Both are crescents; nothing else is shared.
    assert not is_possible(similarity("Reuben Okoya Crescent",
                                      "Sola Adebiyi Crescent"))


def test_different_streets_score_low():
    assert not is_possible(similarity("Ameh Ebute Street", "Railway Road"))


def test_identical_names_score_one():
    assert similarity("Magnus Abe Street", "Magnus Abe Street") == 1.0


def test_empty_or_typeonly_names_do_not_crash():
    assert similarity("Street", "Road") == 0.0
    assert similarity("", "Ameh Ebute") == 0.0
