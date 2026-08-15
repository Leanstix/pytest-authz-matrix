import pytest


@pytest.mark.authz_contract("booking.retrieve")
def test_booking_retrieve_authorization(authz_case):
    authz_case.run()

