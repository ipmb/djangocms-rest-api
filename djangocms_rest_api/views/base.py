# -*- coding: utf-8 -*-
from __future__ import absolute_import, print_function, unicode_literals

from itertools import chain

from cms.models import Page, Placeholder, CMSPlugin
from django.contrib.sites.shortcuts import get_current_site
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import detail_route
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from djangocms_rest_api.serializers import (
    PageSerializer, PlaceHolderSerializer, BasePluginSerializer, get_serializer, get_serializer_class
)
from djangocms_rest_api.views.utils import QuerysetMixin


class PageViewSet(QuerysetMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = PageSerializer
    queryset = Page.objects.all()

    def get_queryset(self):
        site = get_current_site(self.request)
        if self.request.user.is_staff:
            return Page.objects.drafts().on_site(site=site).distinct()
        else:
            return Page.objects.public().on_site(site=site).distinct()


class PlaceHolderViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PlaceHolderSerializer
    queryset = Placeholder.objects.all()

    def get_queryset(self):
        site = get_current_site(self.request)
        if self.request.user.is_staff:
            return Placeholder.objects.filter(page__publisher_is_draft=True, page__site=site).distinct()
        else:
            return Placeholder.objects.filter(page__publisher_is_draft=False, page__site=site).distinct()


class PluginViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = BasePluginSerializer
    queryset = CMSPlugin.objects.all()

    def get_object(self):
        obj = super(PluginViewSet, self).get_object()
        # TODO: check if plugin available for anonymous or current user
        self.instance, self.plugin = obj.get_plugin_instance()
        # Not sure we ned this permissions for retrieve data actions
        if self.action == 'submit_data':
            obj_permissions = [permission() for permission in getattr(self.instance, 'permission_classes', [])]
            for permission in obj_permissions:
                if not permission.has_object_permission(self.request, self, obj):
                    self.permission_denied(
                        self.request, message=getattr(permission, 'message', None)
                    )
        return self.instance

    def get_serializer_class(self):
        # TODO: decide if we need custom serializer here
        if self.action == 'retrieve':
            obj = self.get_object()
            # Do not use model here, since it replaces base serializer with quite limited one, created from model
            return get_serializer_class(plugin=obj.get_plugin_class())
        return super(PluginViewSet, self).get_serializer_class()

    @detail_route(methods=['post', 'put', 'patch'])
    def submit_data(self, request, pk=None, **kwargs):
        obj = self.get_object()
        serializer_class = self.plugin.data_serializer_class
        assert serializer_class, 'data serializer class should be set'
        if request.method == 'POST':
            serializer = serializer_class(data=request.data)
        else:
            raise PermissionDenied('method is not allowed for now')
        if serializer.is_valid():
            if hasattr(self.instance, 'process_data'):
                self.instance.process_data(request, self.instance, serializer)
            else:
                # TODO: Decide if we need to save data by default if process_data method was not implemented
                # point this in documentation
                serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


