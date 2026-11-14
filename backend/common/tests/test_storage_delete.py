"""delete_prefix deletes every page of a listing and nothing outside the prefix."""

from unittest import mock

from common import storage


def _client(pages):
    client = mock.Mock()
    client.get_paginator.return_value.paginate.return_value = pages
    return client


def test_delete_prefix_deletes_all_pages():
    client = _client([{"Contents": [{"Key": "7/a"}, {"Key": "7/b"}]}, {"Contents": [{"Key": "7/c"}]}])

    with mock.patch.object(storage, "s3_client", return_value=client):
        count = storage.delete_prefix("masks", "7/")

    assert count == 3
    client.get_paginator.return_value.paginate.assert_called_once_with(Bucket="masks", Prefix="7/")
    deleted = [c.kwargs["Delete"]["Objects"] for c in client.delete_objects.call_args_list]
    assert deleted == [[{"Key": "7/a"}, {"Key": "7/b"}], [{"Key": "7/c"}]]


def test_delete_prefix_with_nothing_there_makes_no_delete_call():
    client = _client([{}])

    with mock.patch.object(storage, "s3_client", return_value=client):
        assert storage.delete_prefix("masks", "7/") == 0

    client.delete_objects.assert_not_called()


def test_delete_object_deletes_one_key():
    client = mock.Mock()

    with mock.patch.object(storage, "s3_client", return_value=client):
        storage.delete_object("reports", "reports/x/opis.jpg")

    client.delete_object.assert_called_once_with(Bucket="reports", Key="reports/x/opis.jpg")
