# -*- coding: utf-8 -*-
#
# This file is part of Invenio.
# Copyright (C) 2015, 2016, 2017 CERN.
#
# Invenio is free software; you can redistribute it
# and/or modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of the
# License, or (at your option) any later version.
#
# Invenio is distributed in the hope that it will be
# useful, but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Invenio; if not, write to the
# Free Software Foundation, Inc., 59 Temple Place, Suite 330, Boston,
# MA 02111-1307, USA.
#
# In applying this license, CERN does not
# waive the privileges and immunities granted to it by virtue of its status
# as an Intergovernmental Organization or submit itself to any jurisdiction.

"""Database models for access module."""

from __future__ import absolute_import, print_function

from flask_principal import RoleNeed, UserNeed
from invenio_accounts.models import Role, User
from invenio_db import db
from sqlalchemy import UniqueConstraint
from sqlalchemy.event import listen
from sqlalchemy.orm.attributes import get_history

from .proxies import current_access


class ActionNeedMixin(object):
    """Define common attributes for Action needs."""

    id = db.Column(db.Integer, autoincrement=True, primary_key=True)
    """Primary key. It allows the other fields to be nullable."""

    action = db.Column(db.String(80), index=True)
    """Name of the action."""

    exclude = db.Column(db.Boolean(name='exclude'), nullable=False,
                        default=False, server_default='0')
    """If set to True, deny the action, otherwise allow it."""

    argument = db.Column(db.String(255), nullable=True, index=True)
    """Action argument."""

    @classmethod
    def create(cls, action, **kwargs):
        """Create new database row using the provided action need.

        :param action: An object containing a method equal to ``'action'`` and
            a value.
        :param argument: The action argument. If this parameter is not passed,
            then the ``action.argument`` will be used instead. If the
            ``action.argument`` does not exist, ``None`` will be set as
            argument for the new action need.
        :returns: An :class:`invenio_access.models.ActionNeedMixin` instance.
        """
        assert action.method == 'action'
        argument = kwargs.pop('argument', None) or getattr(
            action, 'argument', None)
        return cls(
            action=action.value,
            argument=argument,
            **kwargs
        )

    @classmethod
    def allow(cls, action, **kwargs):
        """Allow the given action need.

        :param action: The action to allow.
        :returns: A :class:`invenio_access.models.ActionNeedMixin` instance.
        """
        return cls.create(action, exclude=False, **kwargs)

    @classmethod
    def deny(cls, action, **kwargs):
        """Deny the given action need.

        :param action: The action to deny.
        :returns: A :class:`invenio_access.models.ActionNeedMixin` instance.
        """
        return cls.create(action, exclude=True, **kwargs)

    @classmethod
    def query_by_action(cls, action, argument=None):
        """Prepare query object with filtered action.

        :param action: The action to deny.
        :param argument: The action argument. If it's ``None`` then, if exists,
            the ``action.argument`` will be taken. In the worst case will be
            set as ``None``. (Default: ``None``)
        :returns: A query object.
        """
        query = cls.query.filter_by(action=action.value)
        argument = argument or getattr(action, 'argument', None)
        if argument is not None:
            query = query.filter(db.or_(
                cls.argument == str(argument),
                cls.argument.is_(None),
            ))
        else:
            query = query.filter(cls.argument.is_(None))
        return query

    @property
    def need(self):
        """Return the need corresponding to this model instance.

        This is an abstract method and will raise NotImplementedError.
        """
        raise NotImplementedError()  # pragma: no cover


class ActionUsers(ActionNeedMixin, db.Model):
    """ActionRoles data model.

    It relates an allowed action with a user.
    """

    __tablename__ = 'access_actionsusers'

    __table_args__ = (UniqueConstraint(
        'action', 'exclude', 'argument', 'user_id',
        name='access_actionsusers_unique'),
    )

    user_id = db.Column(db.Integer(), db.ForeignKey(User.id), nullable=True)

    user = db.relationship("User")

    @property
    def need(self):
        """Return UserNeed instance."""
        return UserNeed(self.user_id)


class ActionRoles(ActionNeedMixin, db.Model):
    """ActionRoles data model.

    It relates an allowed action with a role.
    """

    __tablename__ = 'access_actionsroles'

    __table_args__ = (UniqueConstraint(
        'action', 'exclude', 'argument', 'role_id',
        name='access_actionsroles_unique'),
    )

    role_id = db.Column(db.Integer(), db.ForeignKey(Role.id), nullable=False)

    role = db.relationship("Role")

    @property
    def need(self):
        """Return RoleNeed instance."""
        return RoleNeed(self.role.name)


def _get_action_name(name, argument):
    tokens = [str(name)]
    if argument:
        tokens.append(str(argument))
    return '::'.join(tokens)


def removed_or_inserted_action(mapper, connection, target):
    """Remove the action from cache when an item is inserted or deleted."""
    current_access.delete_action_cache(_get_action_name(target.action,
                                                        target.argument))


def changed_action(mapper, connection, target):
    """Remove the action from cache when an item is updated."""
    action_history = get_history(target, 'action')
    argument_history = get_history(target, 'argument')
    owner_history = get_history(
        target,
        'user' if isinstance(target, ActionUsers) else 'role')

    if action_history.has_changes() or argument_history.has_changes() \
       or owner_history.has_changes():
        current_access.delete_action_cache(_get_action_name(target.action,
                                                            target.argument))
        current_access.delete_action_cache(
            _get_action_name(
                action_history.deleted[0] if action_history.deleted
                else target.action,
                argument_history.deleted[0] if argument_history.deleted
                else target.argument)
        )


listen(ActionUsers, 'after_insert', removed_or_inserted_action)
listen(ActionUsers, 'after_delete', removed_or_inserted_action)
listen(ActionUsers, 'after_update', changed_action)

listen(ActionRoles, 'after_insert', removed_or_inserted_action)
listen(ActionRoles, 'after_delete', removed_or_inserted_action)
listen(ActionRoles, 'after_update', changed_action)
