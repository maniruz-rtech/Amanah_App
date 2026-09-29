"""
Integration tests for notification and WebSocket modules.
"""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import DeliveryStatus, NotificationType
from app.db.models import Device, Notification, User
from app.services.notification import NotificationService
from app.websockets.broadcaster import EventBroadcaster
from app.websockets.handlers import ConnectionManager, WebSocketHandler, manager


class TestNotificationService:
    """Tests for NotificationService."""

    @pytest.fixture
    async def service(self, db_session: AsyncSession) -> NotificationService:
        """Create notification service."""
        return NotificationService(db_session)

    @pytest.fixture
    async def test_user(self, db_session: AsyncSession) -> User:
        """Create test user."""
        user = User(
            id="usr_test_notification",
            username="notif_test",
            password_hash="x",
            organization_id="org_test",
            region_id="reg_test",
            email="notif@test.com",
            phone="+8801234567890",
            is_active=True,
            is_suspended=False,
        )
        db_session.add(user)
        await db_session.flush()
        return user

    @pytest.fixture
    async def test_device(self, db_session: AsyncSession, test_user: User) -> Device:
        """Create test device with FCM token."""
        device = Device(
            id="dev_test_notification",
            user_id=test_user.id,
            device_uuid="uuid-notification-test",
            platform="android",
            app_version="1.0.0",
            push_token="test_fcm_token_notification",
            is_active=True,
        )
        db_session.add(device)
        await db_session.flush()
        return device

    async def test_create_notification(
        self,
        service: NotificationService,
        test_user: User,
    ):
        """Test creating a notification."""
        notification = await service.create_notification(
            user_id=test_user.id,
            notification_type=NotificationType.RESPONDER_ASSIGNMENT,
            title="Assignment",
            body="You have been assigned",
        )

        assert notification.id is not None
        assert notification.user_id == test_user.id
        assert notification.notification_type == NotificationType.RESPONDER_ASSIGNMENT
        assert notification.delivery_status == DeliveryStatus.PENDING

    async def test_create_notification_with_incident(
        self,
        service: NotificationService,
        test_user: User,
    ):
        """Test creating notification with incident link."""
        from datetime import UTC, datetime

        from app.db.models import Incident

        incident_id = "inc_test123"
        service.db.add(
            Incident(
                id=incident_id,
                organization_id="org_test",
                region_id="reg_test",
                created_by_id=test_user.id,
                started_at=datetime.now(UTC),
            )
        )
        await service.db.flush()

        notification = await service.create_notification(
            user_id=test_user.id,
            notification_type=NotificationType.INCIDENT_UPDATE,
            title="Update",
            body="Incident location updated",
            incident_id=incident_id,
        )

        assert notification.incident_id == incident_id

    async def test_dispatch_to_user(
        self,
        service: NotificationService,
        test_user: User,
        test_device: Device,
    ):
        """Test dispatching notification to user's devices."""
        with patch.object(service.fcm_provider, "send", new=AsyncMock(return_value="msg_id_123")) as send:
            notification = await service.dispatch_to_user(
                user_id=test_user.id,
                notification_type=NotificationType.RESPONDER_ASSIGNMENT,
                title="Assignment",
                body="Test assignment",
            )

        send.assert_awaited_once()
        assert send.await_args.kwargs["recipient"] == "test_fcm_token_notification"

        assert notification.delivery_status == DeliveryStatus.SENT
        assert notification.fcm_message_id == "msg_id_123"

    async def test_dispatch_to_user_no_devices(
        self,
        service: NotificationService,
        test_user: User,
    ):
        """Test dispatch fails when user has no devices."""
        notification = await service.dispatch_to_user(
            user_id=test_user.id,
            notification_type=NotificationType.RESPONDER_ASSIGNMENT,
            title="Assignment",
            body="Test",
        )

        assert notification.delivery_status == DeliveryStatus.FAILED
        assert "No active devices" in notification.error_message

    async def test_mark_delivered(
        self,
        service: NotificationService,
        test_user: User,
    ):
        """Test marking notification as delivered."""
        notification = await service.create_notification(
            user_id=test_user.id,
            notification_type=NotificationType.SYSTEM,
            title="Test",
            body="Test message",
        )

        updated = await service.mark_delivered(notification.id)

        assert updated.delivery_status == DeliveryStatus.DELIVERED
        assert updated.delivered_at is not None

    async def test_mark_read(
        self,
        service: NotificationService,
        test_user: User,
    ):
        """Test marking notification as read."""
        notification = await service.create_notification(
            user_id=test_user.id,
            notification_type=NotificationType.SYSTEM,
            title="Test",
            body="Test message",
        )

        # mark_read(user_id, notification_ids) is the batch API used by the endpoint
        count = await service.mark_read(user_id=test_user.id, notification_ids=[notification.id])
        await service.db.refresh(notification)

        assert count == 1
        assert notification.delivery_status == DeliveryStatus.READ
        assert notification.read_at is not None

    async def test_get_user_notifications(
        self,
        service: NotificationService,
        test_user: User,
    ):
        """Test retrieving user notifications."""
        # Create multiple notifications
        for i in range(5):
            await service.create_notification(
                user_id=test_user.id,
                notification_type=NotificationType.SYSTEM,
                title=f"Test {i}",
                body=f"Body {i}",
            )

        notifications, total = await service.get_user_notifications(test_user.id)

        assert len(notifications) == 5
        assert total == 5

    async def test_retry_failed_notifications(
        self,
        service: NotificationService,
        test_user: User,
    ):
        """Test retrying failed notifications."""
        # Create failed notification
        notification = Notification(
            user_id=test_user.id,
            notification_type=NotificationType.SYSTEM,
            title="Test",
            body="Failed message",
            delivery_status=DeliveryStatus.FAILED,
            retry_count=0,
        )
        service.db.add(notification)
        await service.db.flush()

        # Retry
        retry_count = await service.retry_failed_notifications()

        assert retry_count >= 1


class TestConnectionManager:
    """Tests for WebSocket ConnectionManager."""

    @pytest.fixture
    async def conn_manager(self) -> ConnectionManager:
        """Create connection manager."""
        return ConnectionManager()

    async def test_connect_user(self, conn_manager: ConnectionManager):
        """Test registering a user connection."""
        mock_ws = AsyncMock()
        user_id = "usr_test123"

        await conn_manager.connect(mock_ws, user_id)

        assert user_id in conn_manager.active_connections
        assert mock_ws in conn_manager.active_connections[user_id]

    async def test_disconnect_user(self, conn_manager: ConnectionManager):
        """Test unregistering a user connection."""
        mock_ws = AsyncMock()
        user_id = "usr_test123"

        await conn_manager.connect(mock_ws, user_id)
        conn_manager.disconnect(mock_ws, user_id)

        assert user_id not in conn_manager.active_connections

    async def test_broadcast_to_user(self, conn_manager: ConnectionManager):
        """Test broadcasting message to user."""
        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()
        user_id = "usr_test123"

        await conn_manager.connect(mock_ws1, user_id)
        await conn_manager.connect(mock_ws2, user_id)

        message = {"type": "test", "data": "hello"}
        sent = await conn_manager.broadcast_to_user(user_id, message)

        assert sent == 2
        mock_ws1.send_json.assert_called_with(message)
        mock_ws2.send_json.assert_called_with(message)

    async def test_broadcast_to_channel(self, conn_manager: ConnectionManager):
        """Test broadcasting to channel."""
        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()

        await conn_manager.connect(mock_ws1, "usr_1")
        await conn_manager.connect(mock_ws2, "usr_2")

        await conn_manager.subscribe_to_channel(mock_ws1, "incident:inc_123", "usr_1")
        await conn_manager.subscribe_to_channel(mock_ws2, "incident:inc_123", "usr_2")

        message = {"type": "incident_update", "data": "location changed"}
        sent = await conn_manager.broadcast_to_channel("incident:inc_123", message)

        assert sent == 2
        mock_ws1.send_json.assert_called_with(message)
        mock_ws2.send_json.assert_called_with(message)

    async def test_subscribe_to_channel(self, conn_manager: ConnectionManager):
        """Test subscribing to channel."""
        mock_ws = AsyncMock()
        user_id = "usr_test123"
        channel = "incident:inc_123"

        await conn_manager.connect(mock_ws, user_id)
        await conn_manager.subscribe_to_channel(mock_ws, channel, user_id)

        assert channel in conn_manager.channel_connections
        assert mock_ws in conn_manager.channel_connections[channel]

    async def test_unsubscribe_from_channel(self, conn_manager: ConnectionManager):
        """Test unsubscribing from channel."""
        mock_ws = AsyncMock()
        user_id = "usr_test123"
        channel = "incident:inc_123"

        await conn_manager.connect(mock_ws, user_id)
        await conn_manager.subscribe_to_channel(mock_ws, channel, user_id)
        conn_manager.unsubscribe_from_channel(mock_ws, channel, user_id)

        assert mock_ws not in conn_manager.channel_connections.get(channel, set())


class TestWebSocketHandler:
    """Tests for WebSocketHandler."""

    @pytest.fixture
    async def handler(self, db_session: AsyncSession) -> WebSocketHandler:
        """Create WebSocket handler."""
        return WebSocketHandler(db_session)

    @pytest.fixture
    async def test_user_with_token(
        self,
        db_session: AsyncSession,
    ) -> tuple[User, str]:
        """Create test user and token."""
        from app.core.security import create_access_token

        user = User(
            id="usr_ws_test",
            username="ws_test",
            password_hash="x",
            organization_id="org_test",
            region_id="reg_test",
            email="ws@test.com",
            phone="+8801234567890",
            is_active=True,
            is_suspended=False,
        )
        db_session.add(user)
        await db_session.flush()

        token = create_access_token(user_id=user.id, roles=[])
        return user, token

    async def test_authenticate_websocket_valid(
        self,
        handler: WebSocketHandler,
        test_user_with_token: tuple[User, str],
    ):
        """Test authenticating WebSocket with valid token."""
        user, token = test_user_with_token

        authenticated_user = await handler.authenticate_websocket(
            websocket=AsyncMock(),
            token=token,
        )

        assert authenticated_user is not None
        assert authenticated_user.id == user.id

    async def test_authenticate_websocket_missing_token(
        self,
        handler: WebSocketHandler,
    ):
        """Test authenticating WebSocket without token."""
        authenticated_user = await handler.authenticate_websocket(
            websocket=AsyncMock(),
            token=None,
        )

        assert authenticated_user is None

    async def test_authenticate_websocket_invalid_token(
        self,
        handler: WebSocketHandler,
    ):
        """Test authenticating WebSocket with invalid token."""
        authenticated_user = await handler.authenticate_websocket(
            websocket=AsyncMock(),
            token="invalid_token",
        )

        assert authenticated_user is None


class TestEventBroadcaster:
    """Tests for EventBroadcaster."""

    async def test_broadcast_incident_created(self):
        """Test broadcasting incident creation."""
        incident = {
            "id": "inc_test123",
            "title": "Emergency",
            "severity": "critical",
        }

        # Mock manager
        with patch("app.websockets.broadcaster.manager") as mock_manager:
            mock_manager.broadcast_to_channel = AsyncMock(return_value=3)

            await EventBroadcaster.broadcast_incident_created(incident)

            mock_manager.broadcast_to_channel.assert_called_once()
            call_args = mock_manager.broadcast_to_channel.call_args
            assert call_args[0][0] == "incident:inc_test123"

    async def test_broadcast_location_update(self):
        """Test broadcasting location update."""
        incident_id = "inc_test123"
        location = {
            "lat": 23.8103,
            "lng": 90.4125,
            "accuracy_m": 10,
        }

        with patch("app.websockets.broadcaster.manager") as mock_manager:
            mock_manager.broadcast_to_channel = AsyncMock(return_value=2)

            await EventBroadcaster.broadcast_incident_location_update(
                incident_id,
                location,
            )

            mock_manager.broadcast_to_channel.assert_called_once()

    async def test_broadcast_status_change(self):
        """Test broadcasting status change."""
        incident_id = "inc_test123"

        with patch("app.websockets.broadcaster.manager") as mock_manager:
            mock_manager.broadcast_to_channel = AsyncMock(return_value=2)

            await EventBroadcaster.broadcast_incident_status_change(
                incident_id,
                "broadcasting",
                "accepted",
            )

            mock_manager.broadcast_to_channel.assert_called_once()
            call_args = mock_manager.broadcast_to_channel.call_args
            message = call_args[0][1]
            assert message["incident"]["event"] == "status_changed"

    async def test_broadcast_responder_assignment(self):
        """Test broadcasting responder assignment."""
        incident_id = "inc_test123"
        responder_user_id = "usr_responder1"
        assignment = {
            "id": "asgn_test123",
            "incident_id": incident_id,
            "responder_id": responder_user_id,
        }

        with patch("app.websockets.broadcaster.manager") as mock_manager:
            mock_manager.broadcast_to_channel = AsyncMock(return_value=1)

            await EventBroadcaster.broadcast_responder_assignment(
                incident_id,
                responder_user_id,
                assignment,
            )

            # Should broadcast to both responder and incident channels
            assert mock_manager.broadcast_to_channel.call_count == 2

    async def test_broadcast_notification_to_user(self):
        """Test broadcasting notification to user."""
        user_id = "usr_test123"
        notification = {
            "id": "notif_test123",
            "title": "Assignment",
            "body": "You have been assigned",
        }

        with patch("app.websockets.broadcaster.manager") as mock_manager:
            mock_manager.broadcast_to_user = AsyncMock(return_value=1)

            await EventBroadcaster.broadcast_notification_to_user(user_id, notification)

            mock_manager.broadcast_to_user.assert_called_once()
            call_args = mock_manager.broadcast_to_user.call_args
            assert call_args[0][0] == user_id

    async def test_broadcast_incident_channel_notification(self):
        """Test broadcasting to incident channel."""
        incident_id = "inc_test123"
        notification = {
            "id": "notif_test123",
            "title": "Update",
            "body": "Incident status changed",
        }

        with patch("app.websockets.broadcaster.manager") as mock_manager:
            mock_manager.broadcast_to_channel = AsyncMock(return_value=2)

            await EventBroadcaster.broadcast_incident_channel_notification(
                incident_id,
                notification,
            )

            mock_manager.broadcast_to_channel.assert_called_once()


class TestNotificationPayloads:
    """Tests for notification payload design (lock-screen safe)."""

    def test_responder_assignment_payload(self):
        """Test lock-screen safe responder assignment payload."""
        payload = {
            "type": "responder_assignment",
            "assignment_id": "asgn_123",
            "incident_id": "inc_123",
        }

        # Verify payload is minimal
        payload_str = json.dumps(payload)
        assert len(payload_str) < 240  # Lock screen SMS limit

    def test_location_update_payload(self):
        """Test lock-screen safe location update payload."""
        payload = {
            "type": "location_update",
            "incident_id": "inc_123",
            "lat": 23.8103,
            "lng": 90.4125,
        }

        payload_str = json.dumps(payload)
        assert len(payload_str) < 240

    def test_status_change_payload(self):
        """Test lock-screen safe status change payload."""
        payload = {
            "type": "status_changed",
            "incident_id": "inc_123",
            "new_status": "resolved",
        }

        payload_str = json.dumps(payload)
        assert len(payload_str) < 240
