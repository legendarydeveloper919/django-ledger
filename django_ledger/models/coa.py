"""
Django Ledger created by Miguel Sanda <msanda@arrobalytics.com>.
Copyright© EDMA Group Inc licensed under the GPLv3 Agreement.

Contributions to this module:
    * Miguel Sanda <msanda@arrobalytics.com>
    * Pranav P Tulshyan <ptulshyan77@gmail.com>

Chart Of Accounts
_________________

A Chart of Accounts (CoA) is a collection of accounts logically grouped into a distinct set within a
ChartOfAccountModel. The CoA is the backbone of making of any financial statements and it consist of accounts of many
roles, such as cash, accounts receivable, expenses, liabilities, income, etc. For instance, we can have a heading as
"Fixed Assets" in the Balance Sheet, which will consists of Tangible, Intangible Assets. Further, the tangible assets
will consists of multiple accounts like Building, Plant & Equipments, Machinery. So, aggregation of balances of
individual accounts based on the Chart of Accounts and AccountModel roles, helps in preparation of the Financial
Statements.

All EntityModel must have a default CoA to be able to create any type of transaction. Throughout the application,
when no explicit CoA is specified, the default behavior is to use the EntityModel default CoA. **Only ONE Chart of
Accounts can be used when creating Journal Entries**. No commingling between CoAs is allowed in order to preserve the
integrity of the Journal Entry.
"""
from random import choices
from string import ascii_lowercase, digits
from typing import Optional, Union
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from django_ledger.io import (ROOT_COA, ROOT_GROUP_LEVEL_2, ROOT_GROUP_META, ROOT_ASSETS,
                              ROOT_LIABILITIES, ROOT_CAPITAL,
                              ROOT_INCOME, ROOT_COGS, ROOT_EXPENSES)
from django_ledger.models import lazy_loader
from django_ledger.models.accounts import AccountModel, AccountModelQuerySet
from django_ledger.models.mixins import CreateUpdateMixIn, SlugNameMixIn

UserModel = get_user_model()

SLUG_SUFFIX = ascii_lowercase + digits


class ChartOfAccountsModelValidationError(ValidationError):
    pass


class ChartOfAccountModelQuerySet(models.QuerySet):

    def active(self):
        return self.filter(active=True)


class ChartOfAccountModelManager(models.Manager):
    """
    A custom defined ChartOfAccountModelManager that will act as an interface to handling the initial DB queries
    to the ChartOfAccountModel.
    """

    def for_user(self, user_model) -> ChartOfAccountModelQuerySet:
        """
        Fetches a QuerySet of ChartOfAccountModel that the UserModel as access to. May include ChartOfAccountModel from
        multiple Entities. The user has access to bills if:
        1. Is listed as Manager of Entity.
        2. Is the Admin of the Entity.

        Parameters
        ----------
        user_model
            Logged in and authenticated django UserModel instance.

        Examples
        ________
            >>> request_user = self.request.user
            >>> coa_model_qs = ChartOfAccountModel.objects.for_user(user_model=request_user)

        Returns
        _______
        ChartOfAccountQuerySet
            Returns a ChartOfAccountQuerySet with applied filters.
        """
        qs = self.get_queryset()
        return qs.filter(
            (
                    Q(entity__admin=user_model) |
                    Q(entity__managers__in=[user_model])
            )
        ).select_related('entity')

    def for_entity(self, entity_slug, user_model) -> ChartOfAccountModelQuerySet:
        """
        Fetches a QuerySet of ChartOfAccountsModel associated with a specific EntityModel & UserModel.
        May pass an instance of EntityModel or a String representing the EntityModel slug.

        Parameters
        __________

        entity_slug: str or EntityModel
            The entity slug or EntityModel used for filtering the QuerySet.

        user_model
            Logged in and authenticated django UserModel instance.

        Examples
        ________

            >>> request_user = self.request.user
            >>> slug = self.kwargs['entity_slug'] # may come from request kwargs
            >>> coa_model_qs = ChartOfAccountModelManager.objects.for_entity(user_model=request_user, entity_slug=slug)

        Returns
        _______
        ChartOfAccountQuerySet
            Returns a ChartOfAccountQuerySet with applied filters.
        """
        qs = self.for_user(user_model)
        if isinstance(entity_slug, lazy_loader.get_entity_model()):
            return qs.filter(entity=entity_slug).select_related('entity')
        return qs.filter(entity__slug__iexact=entity_slug).select_related('entity')


class ChartOfAccountModelAbstract(SlugNameMixIn, CreateUpdateMixIn):
    """
    Base implementation of Chart of Accounts Model as an Abstract.
    
    2. :func:`CreateUpdateMixIn <django_ledger.models.mixins.SlugMixIn>`
    2. :func:`CreateUpdateMixIn <django_ledger.models.mixins.CreateUpdateMixIn>`
    
    Attributes
    ----------
    uuid : UUID
        This is a unique primary key generated for the table. The default value of this field is uuid4().

    entity: EntityModel
        The EntityModel associated with this Chart of Accounts.

    active: bool
        This determines whether any changes can be done to the Chart of Accounts.
        Inactive Chart of Accounts will not be able to be used in new Transactions.
        Default value is set to False (inactive).

    description: str
        A user generated description for this Chart of Accounts.
    """

    uuid = models.UUIDField(default=uuid4, editable=False, primary_key=True)
    entity = models.ForeignKey('django_ledger.EntityModel',
                               editable=False,
                               verbose_name=_('Entity'),
                               on_delete=models.CASCADE)
    active = models.BooleanField(default=True, verbose_name=_('Is Active'))
    description = models.TextField(verbose_name=_('CoA Description'), null=True, blank=True)
    objects = ChartOfAccountModelManager.from_queryset(queryset_class=ChartOfAccountModelQuerySet)()

    class Meta:
        abstract = True
        ordering = ['-created']
        verbose_name = _('Chart of Account')
        verbose_name_plural = _('Chart of Accounts')
        indexes = [
            models.Index(fields=['entity'])
        ]

    def __str__(self):
        if self.name is not None:
            return f'{self.name} ({self.slug})'
        return self.slug

    def get_coa_root_accounts_qs(self) -> AccountModelQuerySet:
        return self.accountmodel_set.all().is_coa_root()

    def get_coa_root_account(self) -> AccountModel:
        qs = self.get_coa_root_accounts_qs()
        return qs.get(role__exact=ROOT_COA)

    def get_coa_l2_root(self,
                        account_model: AccountModel,
                        root_account_qs: Optional[AccountModelQuerySet] = None,
                        as_queryset: bool = False) -> Union[AccountModelQuerySet, AccountModel]:

        if not account_model.is_root_account():

            if not root_account_qs:
                root_account_qs = self.get_coa_root_accounts_qs()

            if account_model.is_asset():
                qs = root_account_qs.filter(code__exact=ROOT_GROUP_META[ROOT_ASSETS]['code'])
            elif account_model.is_liability():
                qs = root_account_qs.filter(code__exact=ROOT_GROUP_META[ROOT_LIABILITIES]['code'])
            elif account_model.is_capital():
                qs = root_account_qs.filter(code__exact=ROOT_GROUP_META[ROOT_CAPITAL]['code'])
            elif account_model.is_income():
                qs = root_account_qs.filter(code__exact=ROOT_GROUP_META[ROOT_INCOME]['code'])
            elif account_model.is_cogs():
                qs = root_account_qs.filter(code__exact=ROOT_GROUP_META[ROOT_COGS]['code'])
            elif account_model.is_expense():
                qs = root_account_qs.filter(code__exact=ROOT_GROUP_META[ROOT_EXPENSES]['code'])
            else:
                raise ChartOfAccountsModelValidationError(message=f'Unable to locate Balance Sheet'
                                                                  ' root node for account code: '
                                                                  f'{account_model.code} {account_model.name}')
            if as_queryset:
                return qs
            return qs.get()

    def get_non_root_coa_accounts_qs(self) -> AccountModelQuerySet:
        return self.accountmodel_set.all().not_coa_root()

    def get_coa_account_tree(self):
        root_account = self.get_coa_root_account()
        return AccountModel.dump_bulk(parent=root_account)

    def generate_slug(self, raise_exception: bool = False) -> str:
        if self.slug:
            if raise_exception:
                raise ChartOfAccountsModelValidationError(
                    message=_(f'CoA {self.uuid} already has a slug')
                )
            return
        self.slug = f'coa-{self.entity.slug[-5:]}-' + ''.join(choices(SLUG_SUFFIX, k=15))

    def configure(self, raise_exception: bool = True):

        self.generate_slug()

        root_accounts_qs = self.get_coa_root_accounts_qs()
        existing_root_roles = list(set(acc.role for acc in root_accounts_qs))

        if len(existing_root_roles) > 0:
            if raise_exception:
                raise ChartOfAccountsModelValidationError(message=f'Root Nodes already Exist in CoA {self.uuid}...')
            return

        if ROOT_COA not in existing_root_roles:
            # add coa root...
            role_meta = ROOT_GROUP_META[ROOT_COA]
            account_pk = uuid4()
            root_account = AccountModel(
                uuid=account_pk,
                code=role_meta['code'],
                name=role_meta['title'],
                coa_model=self,
                role=ROOT_COA,
                role_default=True,
                active=False,
                locked=True,
                balance_type=role_meta['balance_type']
            )
            AccountModel.add_root(instance=root_account)

            # must retrieve root model after added pero django-treebeard documentation...
            coa_root_account_model = AccountModel.objects.get(uuid__exact=account_pk)

            for root_role in ROOT_GROUP_LEVEL_2:
                if root_role not in existing_root_roles:
                    account_pk = uuid4()
                    role_meta = ROOT_GROUP_META[root_role]
                    coa_root_account_model.add_child(
                        instance=AccountModel(
                            uuid=account_pk,
                            code=role_meta['code'],
                            name=role_meta['title'],
                            coa_model=self,
                            role=root_role,
                            role_default=True,
                            active=False,
                            locked=True,
                            balance_type=role_meta['balance_type']
                        ))

    def is_default(self) -> bool:
        if not self.entity_id:
            return False
        if not self.entity.default_coa_id:
            return False
        return self.entity.default_coa_id == self.uuid

    def is_active(self) -> bool:
        return self.active is True

    def validate_account_model_qs(self, account_model_qs: AccountModelQuerySet):
        if not isinstance(account_model_qs, AccountModelQuerySet):
            raise ChartOfAccountsModelValidationError(
                message='Must pass an instance of AccountModelQuerySet'
            )
        for acc_model in account_model_qs:
            if not acc_model.coa_model_id == self.uuid:
                raise ChartOfAccountsModelValidationError(
                    message=f'Invalid root queryset for CoA {self.name}'
                )

    def allocate_account(self,
                         account_model: AccountModel,
                         root_account_qs: Optional[AccountModelQuerySet] = None):
        """
        Allocates a given account model to the appropriate root account depending on the Account Model Role.

        Parameters
        ----------
        account_model: AccountModel
            The Account Model to Allocate
        root_account_qs:
            The Root Account QuerySet of the Chart Of Accounts to use.
            Will be validated against current CoA Model.

        Returns
        -------
        AccountModel
            The saved and allocated AccountModel.
        """

        if account_model.coa_model_id:
            if account_model.coa_model_id != self.uuid:
                raise ChartOfAccountsModelValidationError(
                    message=f'Invalid Account Model {account_model} for CoA {self}'
                )

        if not root_account_qs:
            root_account_qs = self.get_coa_root_accounts_qs()
        else:
            self.validate_account_model_qs(root_account_qs)

        l2_root_node: AccountModel = self.get_coa_l2_root(
            account_model=account_model,
            root_account_qs=root_account_qs
        )

        account_model.coa_model = self
        l2_root_node.add_child(instance=account_model)
        coa_accounts_qs = self.get_non_root_coa_accounts_qs()
        return coa_accounts_qs.get(uuid__exact=account_model.uuid)

    def create_account(self,
                       code: str,
                       role: str,
                       name: str,
                       balance_type: str,
                       active: bool,
                       root_account_qs: Optional[AccountModelQuerySet] = None):

        account_model = AccountModel(
            code=code,
            name=name,
            role=role,
            active=active,
            balance_type=balance_type
        )
        account_model.clean()

        account_model = self.allocate_account(
            account_model=account_model,
            root_account_qs=root_account_qs
        )
        return account_model

    # ACTIONS -----
    # todo: use these methods once multi CoA features are enabled...
    def lock_all_accounts(self) -> AccountModelQuerySet:
        non_root_accounts_qs = self.get_non_root_coa_accounts_qs()
        non_root_accounts_qs.update(locked=True)
        return non_root_accounts_qs

    def unlock_all_accounts(self) -> AccountModelQuerySet:
        non_root_accounts_qs = self.get_non_root_coa_accounts_qs()
        non_root_accounts_qs.update(locked=False)
        return non_root_accounts_qs

    def mark_as_default(self, commit: bool = False, raise_exception: bool = False, **kwargs):
        """
        Marks the current Chart of Accounts instances as default for the EntityModel.

        Parameters
        ----------
        commit: bool
            Commit the action into the Database. Default is False.
        raise_exception: bool
            Raises exception if Chart of Account model instance is already marked as default.
        """
        if self.is_default():
            if raise_exception:
                raise ChartOfAccountsModelValidationError(
                    message=_(f'The Chart of Accounts {self.slug} is already default')
                )
            return
        self.entity.default_coa_id = self.uuid
        self.clean()
        if commit:
            self.entity.save(
                update_fields=[
                    'default_coa_id',
                    'updated'
                ]
            )

    def mark_as_default_url(self) -> str:
        """
        Returns the URL to mark the current Chart of Accounts instances as Default for the EntityModel.

        Returns
        -------
        str
            The URL as a String.
        """
        return reverse(
            viewname='django_ledger:coa-action-mark-as-default',
            kwargs={
                'entity_slug': self.entity.slug,
                'coa_slug': self.slug
            }
        )

    def can_activate(self) -> bool:
        return self.active is False

    def can_deactivate(self) -> bool:
        return all([
            self.is_active(),
            not self.is_default()
        ])

    def mark_as_active(self, commit: bool = False, raise_exception: bool = False, **kwargs):
        """
        Marks the current Chart of Accounts as Active.

        Parameters
        ----------
        commit: bool
            Commit the action into the Database. Default is False.
        raise_exception: bool
            Raises exception if Chart of Account model instance is already active. Default is False.
        """
        if self.is_active():
            if raise_exception:
                raise ChartOfAccountsModelValidationError(
                    message=_('The Chart of Accounts is currently active.')
                )
            return

        self.active = True
        self.clean()
        if commit:
            self.save(
                update_fields=[
                    'active',
                    'updated'
                ])

    def mark_as_active_url(self) -> str:
        """
        Returns the URL to mark the current Chart of Accounts instances as active.

        Returns
        -------
        str
            The URL as a String.
        """
        return reverse(
            viewname='django_ledger:coa-action-mark-as-active',
            kwargs={
                'entity_slug': self.entity.slug,
                'coa_slug': self.slug
            }
        )

    def mark_as_inactive(self, commit: bool = False, raise_exception: bool = False, **kwargs):
        """
        Marks the current Chart of Accounts as Active.

        Parameters
        ----------
        commit: bool
            Commit the action into the Database. Default is False.
        raise_exception: bool
            Raises exception if Chart of Account model instance is already active. Default is False.
        """
        if not self.is_active():
            if raise_exception:
                raise ChartOfAccountsModelValidationError(
                    message=_('The Chart of Accounts is currently not active.')
                )
            return

        self.active = False
        self.clean()
        if commit:
            self.save(
                update_fields=[
                    'active',
                    'updated'
                ])

    def mark_as_inactive_url(self) -> str:
        """
        Returns the URL to mark the current Chart of Accounts instances as inactive.

        Returns
        -------
        str
            The URL as a String.
        """
        return reverse(
            viewname='django_ledger:coa-action-mark-as-inactive',
            kwargs={
                'entity_slug': self.entity.slug,
                'coa_slug': self.slug
            }
        )

    def get_coa_list_url(self):
        return reverse(
            viewname='django_ledger:coa-list',
            kwargs={
                'entity_slug': self.entity.slug
            }
        )

    def get_absolute_url(self) -> str:
        return reverse(
            viewname='django_ledger:coa-detail',
            kwargs={
                'coa_slug': self.slug,
                'entity_slug': self.entity.slug
            }
        )

    def get_account_list_url(self):
        return reverse(
            viewname='django_ledger:account-list-coa',
            kwargs={
                'entity_slug': self.entity.slug,
                'coa_slug': self.slug
            }
        )

    def get_create_coa_account_url(self):
        return reverse(
            viewname='django_ledger:account-create-coa',
            kwargs={
                'coa_slug': self.slug,
                'entity_slug': self.entity.slug
            }
        )

    def clean(self):
        self.generate_slug()

        if self.is_default() and not self.active:
            raise ChartOfAccountsModelValidationError(
                _('Default Chart of Accounts cannot be deactivated.')
            )


class ChartOfAccountModel(ChartOfAccountModelAbstract):
    """
    Base ChartOfAccounts Model
    """
