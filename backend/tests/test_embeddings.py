from unittest.mock import MagicMock, patch

import pytest

from backend import embeddings


def test_cosine_identical_vectors_is_one():
    v = [1.0, 2.0, 3.0]
    assert embeddings.cosine(v, v) == pytest.approx(1.0, abs=1e-9)


def test_cosine_orthogonal_vectors_is_zero():
    a = [1.0, 0.0]
    b = [0.0, 1.0]
    assert embeddings.cosine(a, b) == pytest.approx(0.0, abs=1e-9)


def test_cosine_opposite_vectors_is_minus_one():
    a = [1.0, 0.0]
    b = [-1.0, 0.0]
    assert embeddings.cosine(a, b) == pytest.approx(-1.0, abs=1e-9)


def test_cosine_handles_empty_or_zero_vectors():
    assert embeddings.cosine([], [1.0]) == 0.0
    assert embeddings.cosine([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_embed_caches_per_model_and_text():
    embeddings.reset_cache()
    fake_resp = MagicMock()
    fake_resp.data = [MagicMock(embedding=[0.1, 0.2, 0.3])]
    fake_client = MagicMock()
    fake_client.embeddings.create.return_value = fake_resp

    with patch("backend.embeddings._client_lazy", return_value=fake_client):
        v1 = embeddings.embed("hello")
        v2 = embeddings.embed("hello")
        v3 = embeddings.embed("world")

    assert v1 == [0.1, 0.2, 0.3]
    assert v1 is v2  # served from cache
    assert v3 == [0.1, 0.2, 0.3]  # different text, hits the api again
    # 2 unique inputs -> 2 api calls
    assert fake_client.embeddings.create.call_count == 2
