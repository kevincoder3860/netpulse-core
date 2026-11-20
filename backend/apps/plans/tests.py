from unittest.mock import MagicMock, patch
from django.test import TestCase
from apps.plans.utils import sync_hotspot_plan_to_mikrotik


class FakePlan:
    def __init__(self, name="1hr_5mbps", is_active=True, upload=2048, download=5120, devices=1):
        self.name = name
        self.is_active = is_active
        self.upload_speed_kbps = upload
        self.download_speed_kbps = download
        self.simultaneous_devices = devices


class MikroTikHotspotSyncTests(TestCase):

    @patch('apps.plans.utils.routeros_api.RouterOsApiPool')
    def test_sync_updates_existing_profile(self, mock_pool_cls):
        mock_pool = MagicMock()
        mock_api = MagicMock()
        mock_resource = MagicMock()

        mock_pool_cls.return_value = mock_pool
        mock_pool.get_api.return_value = mock_api
        mock_api.get_resource.return_value = mock_resource

        # Existing profile found
        mock_resource.get.return_value = [{'id': '*1', 'name': '1hr_5mbps'}]

        plan = FakePlan(name="1hr_5mbps", is_active=True, upload=2048, download=5120, devices=1)
        sync_hotspot_plan_to_mikrotik(plan)

        mock_pool_cls.assert_called_once_with('192.168.56.20', username='admin', password='', port=8728)
        mock_api.get_resource.assert_called_once_with('/ip/hotspot/user/profile')
        mock_resource.set.assert_called_once_with(
            id='*1',
            name='1hr_5mbps',
            rate_limit='2048k/5120k',
            shared_users='1',
        )
        mock_resource.add.assert_not_called()
        mock_resource.remove.assert_not_called()

    @patch('apps.plans.utils.routeros_api.RouterOsApiPool')
    def test_sync_creates_missing_profile(self, mock_pool_cls):
        mock_pool = MagicMock()
        mock_api = MagicMock()
        mock_resource = MagicMock()

        mock_pool_cls.return_value = mock_pool
        mock_pool.get_api.return_value = mock_api
        mock_api.get_resource.return_value = mock_resource

        # Profile does not exist
        mock_resource.get.return_value = []

        plan = FakePlan(name="Daily_10mbps", is_active=True, upload=5120, download=10240, devices=2)
        sync_hotspot_plan_to_mikrotik(plan)

        mock_resource.add.assert_called_once_with(
            name='Daily_10mbps',
            rate_limit='5120k/10240k',
            shared_users='2',
        )
        mock_resource.set.assert_not_called()
        mock_resource.remove.assert_not_called()

    @patch('apps.plans.utils.routeros_api.RouterOsApiPool')
    def test_sync_removes_profile_when_inactive(self, mock_pool_cls):
        mock_pool = MagicMock()
        mock_api = MagicMock()
        mock_resource = MagicMock()

        mock_pool_cls.return_value = mock_pool
        mock_pool.get_api.return_value = mock_api
        mock_api.get_resource.return_value = mock_resource

        # Existing profile found
        mock_resource.get.return_value = [{'id': '*5', 'name': 'Old_Plan'}]

        plan = FakePlan(name="Old_Plan", is_active=False)
        sync_hotspot_plan_to_mikrotik(plan)

        mock_resource.remove.assert_called_once_with(id='*5')
        mock_resource.set.assert_not_called()
        mock_resource.add.assert_not_called()

    @patch('apps.plans.utils.routeros_api.RouterOsApiPool')
    def test_sync_renames_profile_using_old_name(self, mock_pool_cls):
        mock_pool = MagicMock()
        mock_api = MagicMock()
        mock_resource = MagicMock()

        mock_pool_cls.return_value = mock_pool
        mock_pool.get_api.return_value = mock_api
        mock_api.get_resource.return_value = mock_resource

        # Profile found under old_name
        mock_resource.get.return_value = [{'id': '*2', 'name': 'Old_Name'}]

        plan = FakePlan(name="New_Name", is_active=True, upload=1024, download=2048, devices=1)
        sync_hotspot_plan_to_mikrotik(plan, old_name='Old_Name')

        mock_resource.set.assert_called_once_with(
            id='*2',
            name='New_Name',
            rate_limit='1024k/2048k',
            shared_users='1',
        )

    @patch('apps.plans.utils.routeros_api.RouterOsApiPool')
    def test_sync_fail_safe_on_connection_error(self, mock_pool_cls):
        mock_pool_cls.side_effect = Exception("Router connection timed out")

        plan = FakePlan(name="Plan_Timeout", is_active=True)
        # Should not raise exception
        try:
            sync_hotspot_plan_to_mikrotik(plan)
        except Exception as exc:
            self.fail(f"sync_hotspot_plan_to_mikrotik crashed on connection error: {exc}")

    @patch('apps.billing.views.sync_hotspot_plan_to_mikrotik')
    def test_viewset_perform_create_and_update(self, mock_sync):
        from apps.billing.views import HotspotPlanViewSet

        viewset = HotspotPlanViewSet()

        # Test perform_create
        mock_serializer = MagicMock()
        created_plan = FakePlan(name="Created_Plan")
        mock_serializer.save.return_value = created_plan
        viewset.perform_create(mock_serializer)
        mock_sync.assert_called_with(created_plan)

        # Test perform_update
        existing_instance = FakePlan(name="Original_Plan_Name")
        viewset.get_object = MagicMock(return_value=existing_instance)
        updated_plan = FakePlan(name="Updated_Plan_Name")
        mock_update_serializer = MagicMock()
        mock_update_serializer.save.return_value = updated_plan
        viewset.perform_update(mock_update_serializer)
        mock_sync.assert_called_with(updated_plan, old_name="Original_Plan_Name")
