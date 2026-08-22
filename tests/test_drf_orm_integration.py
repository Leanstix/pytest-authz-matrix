from __future__ import annotations

from textwrap import dedent

import pytest


def _write_project_file(pytester: pytest.Pytester, path: str, content: str) -> None:
    target = pytester.path / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(dedent(content).lstrip(), encoding="utf-8")


def test_model_viewset_enforces_database_tenant_and_object_permissions(
    pytester: pytest.Pytester,
) -> None:
    _write_project_file(pytester, "orm_project/__init__.py", "")
    _write_project_file(
        pytester,
        "orm_project/settings.py",
        """
        from pathlib import Path

        BASE_DIR = Path(__file__).resolve().parent.parent
        SECRET_KEY = 'test'
        DEBUG = False
        ALLOWED_HOSTS = ['testserver']
        ROOT_URLCONF = 'orm_project.urls'
        INSTALLED_APPS = [
            'django.contrib.auth',
            'django.contrib.contenttypes',
            'rest_framework',
            'bookings',
        ]
        DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': BASE_DIR / 'db.sqlite3',
            }
        }
        DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
        USE_TZ = True
        REST_FRAMEWORK = {'UNAUTHENTICATED_USER': None}
        """,
    )
    _write_project_file(
        pytester,
        "orm_project/urls.py",
        """
        from django.urls import include, path
        from rest_framework.routers import SimpleRouter

        from bookings.views import BookingViewSet

        router = SimpleRouter()
        router.register('bookings', BookingViewSet, basename='booking')

        urlpatterns = [path('api/', include(router.urls))]
        """,
    )
    _write_project_file(pytester, "bookings/__init__.py", "")
    _write_project_file(
        pytester,
        "bookings/apps.py",
        """
        from django.apps import AppConfig


        class BookingsConfig(AppConfig):
            default_auto_field = 'django.db.models.BigAutoField'
            name = 'bookings'
        """,
    )
    _write_project_file(
        pytester,
        "bookings/models.py",
        """
        import uuid

        from django.db import models


        class Booking(models.Model):
            public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
            tenant = models.CharField(max_length=50)
            owner_key = models.CharField(max_length=50)
            title = models.CharField(max_length=100)
            state = models.CharField(max_length=20, default='draft')

            class Meta:
                ordering = ('id',)
        """,
    )
    _write_project_file(pytester, "bookings/migrations/__init__.py", "")
    _write_project_file(
        pytester,
        "bookings/migrations/0001_initial.py",
        """
        import uuid

        from django.db import migrations, models


        class Migration(migrations.Migration):
            initial = True
            dependencies = []
            operations = [
                migrations.CreateModel(
                    name='Booking',
                    fields=[
                        (
                            'id',
                            models.BigAutoField(
                                auto_created=True,
                                primary_key=True,
                                serialize=False,
                                verbose_name='ID',
                            ),
                        ),
                        (
                            'public_id',
                            models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
                        ),
                        ('tenant', models.CharField(max_length=50)),
                        ('owner_key', models.CharField(max_length=50)),
                        ('title', models.CharField(max_length=100)),
                        ('state', models.CharField(default='draft', max_length=20)),
                    ],
                    options={'ordering': ('id',)},
                ),
            ]
        """,
    )
    _write_project_file(
        pytester,
        "bookings/serializers.py",
        """
        from rest_framework import serializers

        from bookings.models import Booking


        class BookingSerializer(serializers.ModelSerializer):
            class Meta:
                model = Booking
                fields = ('public_id', 'tenant', 'owner_key', 'title', 'state')
                read_only_fields = ('public_id', 'tenant', 'owner_key')
        """,
    )
    _write_project_file(
        pytester,
        "bookings/views.py",
        """
        from rest_framework.authentication import BasicAuthentication
        from rest_framework.permissions import BasePermission, IsAuthenticated
        from rest_framework.viewsets import ModelViewSet

        from bookings.models import Booking
        from bookings.serializers import BookingSerializer


        class IsBookingOwner(BasePermission):
            def has_object_permission(self, request, view, obj):
                return obj.owner_key == request.user.key


        class BookingViewSet(ModelViewSet):
            serializer_class = BookingSerializer
            authentication_classes = (BasicAuthentication,)
            permission_classes = (IsAuthenticated, IsBookingOwner)
            lookup_field = 'public_id'

            def get_queryset(self):
                return Booking.objects.filter(tenant=self.request.user.tenant)

            def perform_create(self, serializer):
                serializer.save(
                    tenant=self.request.user.tenant,
                    owner_key=self.request.user.key,
                )
        """,
    )
    _write_project_file(
        pytester,
        "pytest.ini",
        """
        [pytest]
        DJANGO_SETTINGS_MODULE = orm_project.settings
        """,
    )
    _write_project_file(
        pytester,
        "conftest.py",
        """
        from dataclasses import dataclass

        import pytest
        from rest_framework.test import APIClient

        from bookings.models import Booking


        @dataclass
        class Actor:
            key: str
            tenant: str
            is_authenticated: bool = True


        def actor_client(key, tenant):
            client = APIClient()
            client.force_authenticate(Actor(key=key, tenant=tenant))
            return client


        @pytest.fixture
        def owner_client():
            return actor_client('owner', 'tenant-a')


        @pytest.fixture
        def tenant_b_client():
            return actor_client('tenant-b-owner', 'tenant-b')


        @pytest.fixture
        def anonymous_client():
            return APIClient()


        @pytest.fixture
        def booking_matrix(db):
            return {
                'owned': Booking.objects.create(
                    tenant='tenant-a', owner_key='owner', title='Owned booking'
                ),
                'same_tenant': Booking.objects.create(
                    tenant='tenant-a', owner_key='someone-else', title='Same tenant booking'
                ),
                'foreign': Booking.objects.create(
                    tenant='tenant-b', owner_key='tenant-b-owner', title='Foreign booking'
                ),
            }


        @pytest.fixture
        def create_payload():
            return {'title': 'Created through matrix', 'state': 'confirmed'}


        @pytest.fixture
        def replace_payload():
            return {'title': 'Fully replaced', 'state': 'confirmed'}


        @pytest.fixture
        def partial_payload():
            return {'state': 'cancelled'}
        """,
    )
    _write_project_file(
        pytester,
        "authz-matrix.yml",
        """
        version: 1
        actors:
          owner: owner_client
          tenant_b_owner: tenant_b_client
          anonymous: anonymous_client
        resources:
          booking:
            fixture: booking_matrix
            lookup: public_id
        outcomes:
          created: [201]
          deleted: [204]
        contracts:
          booking.list:
            method: GET
            path: /api/bookings/
            route_name: booking-list
            matrix:
              owner: allow
              tenant_b_owner: allow
              anonymous: unauthenticated
          booking.create:
            method: POST
            path: /api/bookings/
            route_name: booking-list
            request:
              data_fixture: create_payload
              format: json
            matrix:
              owner: created
              anonymous: unauthenticated
          booking.retrieve:
            method: GET
            path: /api/bookings/{resource}/
            route_name: booking-detail
            resource: booking
            matrix:
              owner:
                owned: allow
                same_tenant: deny
                foreign: conceal
              tenant_b_owner:
                owned: conceal
                same_tenant: conceal
                foreign: allow
              anonymous:
                owned: unauthenticated
                same_tenant: unauthenticated
                foreign: unauthenticated
          booking.replace:
            method: PUT
            path: /api/bookings/{resource}/
            route_name: booking-detail
            resource: booking
            request:
              data_fixture: replace_payload
              format: json
            matrix:
              owner:
                owned: allow
                same_tenant: deny
                foreign: conceal
          booking.partial:
            method: PATCH
            path: /api/bookings/{resource}/
            route_name: booking-detail
            resource: booking
            request:
              data_fixture: partial_payload
              format: json
            matrix:
              owner:
                owned: allow
                same_tenant: deny
                foreign: conceal
          booking.delete:
            method: DELETE
            path: /api/bookings/{resource}/
            route_name: booking-detail
            resource: booking
            matrix:
              owner:
                owned: deleted
                same_tenant: deny
                foreign: conceal
        """,
    )
    _write_project_file(
        pytester,
        "test_authorization.py",
        """
        import pytest

        from bookings.models import Booking


        pytestmark = pytest.mark.django_db


        @pytest.mark.authz_contract('booking.list')
        def test_booking_list_is_tenant_scoped(authz_case, booking_matrix):
            response = authz_case.run()
            if authz_case.actor == 'owner':
                assert {item['public_id'] for item in response.data} == {
                    str(booking_matrix['owned'].public_id),
                    str(booking_matrix['same_tenant'].public_id),
                }
            elif authz_case.actor == 'tenant_b_owner':
                assert {item['public_id'] for item in response.data} == {
                    str(booking_matrix['foreign'].public_id),
                }


        @pytest.mark.authz_contract('booking.create')
        def test_booking_create_persists_actor_tenant_and_owner(authz_case):
            before = Booking.objects.count()
            response = authz_case.run()
            if authz_case.outcome == 'created':
                created = Booking.objects.get(public_id=response.data['public_id'])
                assert Booking.objects.count() == before + 1
                assert created.tenant == 'tenant-a'
                assert created.owner_key == 'owner'
                assert created.title == 'Created through matrix'
                assert created.state == 'confirmed'
            else:
                assert Booking.objects.count() == before


        @pytest.mark.authz_contract('booking.retrieve')
        def test_booking_retrieve_uses_queryset_and_object_permission(authz_case):
            response = authz_case.run()
            if authz_case.outcome == 'allow':
                assert response.data['public_id'] == str(authz_case.resource.public_id)


        @pytest.mark.authz_contract('booking.replace')
        def test_booking_replace_persists_only_for_the_owner(authz_case):
            booking = authz_case.resource
            original = (booking.title, booking.state)
            response = authz_case.execute()
            booking.refresh_from_db()
            if authz_case.outcome == 'allow':
                assert (booking.title, booking.state) == ('Fully replaced', 'confirmed')
            else:
                assert (booking.title, booking.state) == original
            authz_case.assert_response(response)


        @pytest.mark.authz_contract('booking.partial')
        def test_booking_partial_update_persists_only_for_the_owner(authz_case):
            booking = authz_case.resource
            original = booking.state
            response = authz_case.execute()
            booking.refresh_from_db()
            if authz_case.outcome == 'allow':
                assert booking.state == 'cancelled'
            else:
                assert booking.state == original
            authz_case.assert_response(response)


        @pytest.mark.django_db(transaction=True)
        @pytest.mark.authz_contract('booking.delete')
        def test_booking_delete_changes_database_only_for_the_owner(authz_case):
            booking_id = authz_case.resource.pk
            response = authz_case.execute()
            exists = Booking.objects.filter(pk=booking_id).exists()
            assert exists is (authz_case.outcome != 'deleted')
            authz_case.assert_response(response)
        """,
    )

    result = pytester.runpytest_subprocess(
        "-q",
        "--authz-report",
        "--authz-require-complete",
        "--authz-fail-under=100",
    )

    result.assert_outcomes(passed=23)
    result.stdout.fnmatch_lines(
        [
            "authorization cases: 23/23 complete, 23 executed, 23 asserted, 23 passed, 0 failed",
            "authorization contracts: 6/6 complete",
            "DRF route coverage: 6/6 (100.0%)",
        ]
    )
