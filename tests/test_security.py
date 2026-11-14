import hashlib

import pytest

from blakkisvuohi.security import Crypto, DataKey, DecryptionError


def test_pseudonyms_are_deterministic_and_keyed():
    a, b = Crypto("a" * 40), Crypto("b" * 40)
    assert a.user_id(62461364) == a.user_id(62461364)
    assert a.user_id(62461364) != a.user_id(62461365)
    assert a.user_id(62461364) != b.user_id(62461364)  # useless without the key
    assert len(a.user_id(1)) == 64


def test_pseudonyms_are_not_a_plain_sha256_of_the_id():
    """The old scheme (unsalted sha256) could be brute forced from a leaked database."""
    assert Crypto("a" * 40).user_id(62461364) != hashlib.sha256(b"62461364").hexdigest()


def test_user_and_group_pseudonyms_do_not_correlate():
    crypto = Crypto("a" * 40)
    assert crypto.user_id(12345) != crypto.group_id(12345)


def test_webhook_path_is_stable_and_secret_dependent():
    assert Crypto("a" * 40).webhook_path() == Crypto("a" * 40).webhook_path()
    assert Crypto("a" * 40).webhook_path() != Crypto("b" * 40).webhook_path()
    assert Crypto("a" * 40).webhook_path().startswith("/webhook/")


# -- data keys ------------------------------------------------------------------------------------


def test_sealed_values_roundtrip_and_are_randomised():
    key = Crypto.new_data_key()
    value = {"nick": "Anto Keinänen", "w": 80}
    a = key.seal(value, aad="u1:profile")
    b = key.seal(value, aad="u1:profile")
    assert a != b  # random nonce: equal data is not visible in the database
    assert "Anto" not in a
    assert key.open(a, aad="u1:profile") == value


def test_every_user_has_their_own_key():
    a, b = Crypto.new_data_key(), Crypto.new_data_key()
    token = a.seal({"x": 1}, aad="u1:profile")
    with pytest.raises(DecryptionError):
        b.open(token, aad="u1:profile")


def test_a_ciphertext_is_bound_to_its_owner_and_purpose():
    key = Crypto.new_data_key()
    token = key.seal({"x": 1}, aad="u1:profile")
    with pytest.raises(DecryptionError):
        key.open(token, aad="u2:profile")  # another user's row
    with pytest.raises(DecryptionError):
        key.open(token, aad="u1:drinks")  # used as another kind of blob


def test_tampering_is_detected():
    key = Crypto.new_data_key()
    token = key.seal({"x": 1}, aad="a")
    flipped = token[:-2] + ("AA" if token[-2:] != "AA" else "BB")
    with pytest.raises(DecryptionError):
        key.open(flipped, aad="a")
    for garbage in ("", "v1.", "v2.abcd", "nonsense", "v1.!!!"):
        with pytest.raises(DecryptionError):
            key.open(garbage, aad="a")


def test_ciphertext_length_hides_the_amount_of_data():
    key = Crypto.new_data_key()
    few = key.seal([[1, 2, "x"]] * 3, aad="a", pad_to=2048)
    more = key.seal([[1, 2, "x"]] * 30, aad="a", pad_to=2048)
    assert len(few) == len(more)
    assert key.open(more, aad="a") == [[1, 2, "x"]] * 30  # the padding is invisible
    much = key.seal([[1, 2, "x"]] * 3000, aad="a", pad_to=2048)
    assert len(much) > len(few)


def test_keys_are_wrapped_under_the_master_key_and_bound_to_the_user():
    crypto = Crypto("a" * 40)
    key = crypto.new_data_key()
    wrapped = crypto.wrap(key, "u1")
    token = key.seal({"secret": 1}, aad="u1:profile")
    assert crypto.unwrap(wrapped, "u1").open(token, aad="u1:profile") == {"secret": 1}
    with pytest.raises(DecryptionError):
        crypto.unwrap(wrapped, "u2")  # a key cannot be moved to another user
    with pytest.raises(DecryptionError):
        Crypto("b" * 40).unwrap(wrapped, "u1")  # and is useless without the master key


def test_keys_do_not_leak_through_repr():
    assert "DataKey(<hidden>)" == repr(DataKey(b"k" * 32))
    with pytest.raises(ValueError, match="32 bytes"):
        DataKey(b"short")
