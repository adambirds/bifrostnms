from tortoise import migrations
from tortoise.migrations import operations as ops
import functools
from json import dumps, loads
from tortoise.fields.base import OnDelete
from uuid import uuid4
from tortoise import fields

class Migration(migrations.Migration):
    initial = True

    operations = [
        ops.CreateModel(
            name='Realm',
            fields=[
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ('updated_at', fields.DatetimeField(auto_now=True, auto_now_add=False)),
                ('id', fields.UUIDField(primary_key=True, default=uuid4, unique=True, db_index=True)),
                ('name', fields.CharField(max_length=200)),
                ('slug', fields.CharField(unique=True, db_index=True, max_length=120)),
                ('is_active', fields.BooleanField(default=True)),
            ],
            options={'table': 'realm', 'app': 'models', 'pk_attr': 'id'},
            bases=['TimestampedModel'],
        ),
        ops.CreateModel(
            name='User',
            fields=[
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ('updated_at', fields.DatetimeField(auto_now=True, auto_now_add=False)),
                ('id', fields.UUIDField(primary_key=True, default=uuid4, unique=True, db_index=True)),
                ('email', fields.CharField(unique=True, db_index=True, max_length=320)),
                ('password_hash', fields.CharField(max_length=255)),
                ('first_name', fields.CharField(max_length=150)),
                ('last_name', fields.CharField(max_length=150)),
                ('is_active', fields.BooleanField(default=True)),
                ('is_staff', fields.BooleanField(default=False)),
                ('email_verified', fields.BooleanField(default=False)),
            ],
            options={'table': 'user', 'app': 'models', 'pk_attr': 'id'},
            bases=['TimestampedModel'],
        ),
        ops.CreateModel(
            name='AuthenticationChallenge',
            fields=[
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ('updated_at', fields.DatetimeField(auto_now=True, auto_now_add=False)),
                ('id', fields.UUIDField(primary_key=True, default=uuid4, unique=True, db_index=True)),
                ('user', fields.ForeignKeyField('models.User', source_field='user_id', null=True, db_constraint=True, to_field='id', related_name='authentication_challenges', on_delete=OnDelete.CASCADE)),
                ('challenge_type', fields.CharField(db_index=True, max_length=32)),
                ('challenge_hash', fields.CharField(unique=True, db_index=True, max_length=64)),
                ('expires_at', fields.DatetimeField(db_index=True, auto_now=False, auto_now_add=False)),
                ('consumed_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
                ('metadata', fields.JSONField(default=dict, encoder=functools.partial(dumps, separators=(',', ':')), decoder=loads)),
            ],
            options={'table': 'authenticationchallenge', 'app': 'models', 'pk_attr': 'id'},
            bases=['TimestampedModel'],
        ),
        ops.CreateModel(
            name='RealmMembership',
            fields=[
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ('updated_at', fields.DatetimeField(auto_now=True, auto_now_add=False)),
                ('id', fields.UUIDField(primary_key=True, default=uuid4, unique=True, db_index=True)),
                ('user', fields.ForeignKeyField('models.User', source_field='user_id', db_constraint=True, to_field='id', related_name='memberships', on_delete=OnDelete.CASCADE)),
                ('realm', fields.ForeignKeyField('models.Realm', source_field='realm_id', db_constraint=True, to_field='id', related_name='memberships', on_delete=OnDelete.CASCADE)),
                ('role', fields.CharField(default='owner', max_length=32)),
            ],
            options={'table': 'realmmembership', 'app': 'models', 'unique_together': (('user', 'realm'),), 'pk_attr': 'id'},
            bases=['TimestampedModel'],
        ),
        ops.CreateModel(
            name='RecoveryCode',
            fields=[
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ('updated_at', fields.DatetimeField(auto_now=True, auto_now_add=False)),
                ('id', fields.UUIDField(primary_key=True, default=uuid4, unique=True, db_index=True)),
                ('user', fields.ForeignKeyField('models.User', source_field='user_id', db_constraint=True, to_field='id', related_name='recovery_codes', on_delete=OnDelete.CASCADE)),
                ('code_hash', fields.CharField(db_index=True, max_length=64)),
                ('used_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
            ],
            options={'table': 'recoverycode', 'app': 'models', 'pk_attr': 'id'},
            bases=['TimestampedModel'],
        ),
        ops.CreateModel(
            name='TwoFactorMethod',
            fields=[
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ('updated_at', fields.DatetimeField(auto_now=True, auto_now_add=False)),
                ('id', fields.UUIDField(primary_key=True, default=uuid4, unique=True, db_index=True)),
                ('user', fields.ForeignKeyField('models.User', source_field='user_id', db_constraint=True, to_field='id', related_name='two_factor_methods', on_delete=OnDelete.CASCADE)),
                ('method_type', fields.CharField(default='totp', max_length=32)),
                ('secret_encrypted', fields.TextField(unique=False)),
                ('name', fields.CharField(default='Authenticator app', max_length=120)),
                ('is_enabled', fields.BooleanField(default=False)),
                ('verified_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
                ('last_used_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
            ],
            options={'table': 'twofactormethod', 'app': 'models', 'unique_together': (('user', 'method_type'),), 'pk_attr': 'id'},
            bases=['TimestampedModel'],
        ),
        ops.CreateModel(
            name='WebAuthnCredential',
            fields=[
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ('updated_at', fields.DatetimeField(auto_now=True, auto_now_add=False)),
                ('id', fields.UUIDField(primary_key=True, default=uuid4, unique=True, db_index=True)),
                ('user', fields.ForeignKeyField('models.User', source_field='user_id', db_constraint=True, to_field='id', related_name='webauthn_credentials', on_delete=OnDelete.CASCADE)),
                ('credential_id', fields.CharField(unique=True, max_length=1024)),
                ('public_key', fields.TextField(unique=False)),
                ('sign_count', fields.BigIntField(default=0)),
                ('name', fields.CharField(default='Passkey', max_length=120)),
                ('device_type', fields.CharField(default='', max_length=64)),
                ('backed_up', fields.BooleanField(default=False)),
                ('transports', fields.JSONField(default=list, encoder=functools.partial(dumps, separators=(',', ':')), decoder=loads)),
                ('last_used_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
            ],
            options={'table': 'webauthncredential', 'app': 'models', 'pk_attr': 'id'},
            bases=['TimestampedModel'],
        ),
    ]
