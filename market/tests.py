from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from market.models import Listing, Message, Thread


class AccessControlTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.seller = User.objects.create_user("seller", password="test-password")
        cls.buyer = User.objects.create_user("buyer", password="test-password")
        cls.outsider = User.objects.create_user("outsider", password="test-password")
        cls.staff = User.objects.create_user("staff", password="test-password", is_staff=True)
        cls.listing = Listing.objects.create(
            owner=cls.seller, title="Test book", description="Good condition",
            price="10.00", category="books", seller_note="Private pickup instructions",
        )
        cls.thread = Thread.objects.create(listing=cls.listing, buyer=cls.buyer)
        Message.objects.create(thread=cls.thread, sender=cls.seller, body="Private message")

    def listing_data(self, **changes):
        data = {
            "title": "Updated book", "description": "Still good", "price": "12.00",
            "category": "books", "seller_note": "Updated private note",
        }
        data.update(changes)
        return data

    def test_other_users_cannot_open_edit_form_or_read_seller_note(self):
        for user in (self.buyer, self.outsider, self.staff):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(reverse("listing_edit", args=[self.listing.pk]))
                self.assertEqual(response.status_code, 404)
                self.assertNotContains(response, "Private pickup instructions", status_code=404)

    def test_other_users_cannot_change_sell_or_remove_listing(self):
        for user in (self.buyer, self.outsider, self.staff):
            self.client.force_login(user)
            for route in ("listing_edit", "listing_sold", "listing_delete"):
                with self.subTest(user=user.username, route=route):
                    response = self.client.post(
                        reverse(route, args=[self.listing.pk]), self.listing_data()
                    )
                    self.assertEqual(response.status_code, 404)
                    self.listing.refresh_from_db()
                    self.assertEqual(self.listing.title, "Test book")
                    self.assertEqual(self.listing.status, "available")
                    self.assertEqual(self.listing.seller_note, "Private pickup instructions")

    def test_seller_can_edit_sell_and_remove_own_listing(self):
        self.client.force_login(self.seller)
        self.assertEqual(self.client.get(reverse("listing_edit", args=[self.listing.pk])).status_code, 200)
        response = self.client.post(reverse("listing_edit", args=[self.listing.pk]), self.listing_data())
        self.assertEqual(response.status_code, 302)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.title, "Updated book")
        self.assertEqual(self.listing.seller_note, "Updated private note")
        for route, status in (("listing_sold", "sold"), ("listing_delete", "removed")):
            self.assertEqual(self.client.post(reverse(route, args=[self.listing.pk])).status_code, 302)
            self.listing.refresh_from_db()
            self.assertEqual(self.listing.status, status)

    def test_new_listing_owner_is_assigned_by_server(self):
        self.client.force_login(self.outsider)
        response = self.client.post(reverse("listing_new"), self.listing_data(owner=self.seller.pk))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Listing.objects.get(title="Updated book").owner, self.outsider)

    def test_only_thread_participants_can_read_or_reply(self):
        url = reverse("thread_detail", args=[self.thread.pk])
        for user in (self.outsider, self.staff):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(url)
                self.assertEqual(response.status_code, 404)
                self.assertNotContains(response, "Private message", status_code=404)
                self.assertEqual(self.client.post(url, {"body": "Injected reply"}).status_code, 404)
        self.assertEqual(self.thread.messages.count(), 1)

    def test_buyer_and_seller_can_read_and_reply(self):
        url = reverse("thread_detail", args=[self.thread.pk])
        for user in (self.buyer, self.seller):
            self.client.force_login(user)
            self.assertContains(self.client.get(url), "Private message")
            self.assertEqual(self.client.post(url, {"body": "My reply"}).status_code, 302)
            self.assertTrue(self.thread.messages.filter(sender=user, body="My reply").exists())

    def test_start_thread_uses_current_buyer_and_reuses_thread(self):
        self.client.force_login(self.outsider)
        url = reverse("start_thread", args=[self.listing.pk])
        self.assertEqual(self.client.get(url).status_code, 302)
        self.assertEqual(self.client.get(url).status_code, 302)
        self.assertEqual(Thread.objects.filter(listing=self.listing, buyer=self.outsider).count(), 1)

    def test_profile_cannot_grant_privileges_even_with_forged_fields(self):
        self.client.force_login(self.outsider)
        response = self.client.post(reverse("profile"), {
            "first_name": "Updated", "last_name": "Name", "email": "updated@example.test",
            "is_staff": "on", "is_superuser": "on", "is_active": "", "username": "stolen",
        })
        self.assertEqual(response.status_code, 302)
        self.outsider.refresh_from_db()
        self.assertEqual(self.outsider.first_name, "Updated")
        self.assertEqual(self.outsider.email, "updated@example.test")
        self.assertFalse(self.outsider.is_staff)
        self.assertFalse(self.outsider.is_superuser)
        self.assertTrue(self.outsider.is_active)
        self.assertEqual(self.outsider.username, "outsider")
        self.assertNotContains(self.client.get(reverse("desk")), "Department hold closet", status_code=403)

    def test_profile_does_not_expose_staff_field(self):
        self.client.force_login(self.outsider)
        self.assertNotContains(self.client.get(reverse("profile")), 'name="is_staff"')

    def test_staff_profile_update_preserves_existing_staff_access(self):
        self.client.force_login(self.staff)
        self.client.post(reverse("profile"), {"first_name": "Staff", "last_name": "Member", "email": "staff@example.test"})
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.is_staff)
        self.assertContains(self.client.get(reverse("desk")), "Department hold closet")

    def test_nonstaff_cannot_access_desk(self):
        self.client.force_login(self.outsider)
        self.assertNotContains(self.client.get(reverse("desk")), "Department hold closet", status_code=403)

    def test_public_detail_hides_owner_actions_from_other_users(self):
        self.client.force_login(self.buyer)
        response = self.client.get(reverse("listing_detail", args=[self.listing.pk]))
        self.assertContains(response, "Message seller")
        self.assertNotContains(response, "Edit listing")
        self.assertNotContains(response, "Mark sold")
        self.assertNotContains(response, "Private pickup instructions")
        self.client.force_login(self.seller)
        response = self.client.get(reverse("listing_detail", args=[self.listing.pk]))
        self.assertContains(response, "Edit listing")
        self.assertContains(response, "Mark sold")

    def test_anonymous_public_pages_and_protected_routes(self):
        for url in ("/", "/?category=books", "/login/", "/register/", reverse("listing_detail", args=[self.listing.pk])):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
        for route, args in (
            ("listing_new", []), ("listing_edit", [self.listing.pk]),
            ("start_thread", [self.listing.pk]), ("thread_detail", [self.thread.pk]),
            ("mine", []), ("profile", []), ("desk", []),
        ):
            with self.subTest(route=route):
                self.assertEqual(self.client.get(reverse(route, args=args)).status_code, 302)
        for route in ("listing_sold", "listing_delete"):
            self.assertEqual(self.client.post(reverse(route, args=[self.listing.pk])).status_code, 302)

    def test_sold_and_delete_require_post(self):
        self.client.force_login(self.seller)
        for route in ("listing_sold", "listing_delete"):
            self.assertEqual(self.client.get(reverse(route, args=[self.listing.pk])).status_code, 405)

    def test_mine_only_shows_participant_threads(self):
        self.client.force_login(self.outsider)
        self.assertNotContains(self.client.get(reverse("mine")), reverse("thread_detail", args=[self.thread.pk]))
        for user in (self.buyer, self.seller):
            self.client.force_login(user)
            self.assertContains(self.client.get(reverse("mine")), reverse("thread_detail", args=[self.thread.pk]))
