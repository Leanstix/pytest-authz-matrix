import pytest


@pytest.mark.authz_contract("booking.retrieve")
def test_booking_retrieve_authorization(authz_case):
    authz_case.run()


@pytest.mark.authz_contract("booking.update")
def test_booking_update_authorization(authz_case):
    authz_case.run()
