# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# pylint: disable=too-many-lines, too-many-public-methods, too-many-ancestors

import logging
import warnings
from collections import abc
from datetime import datetime
from json import dumps
from typing import List, Union, Optional

from coreapi.exceptions import ErrorMessage
from version_utils import rpm

from adcm_client.base import (
    ActionHasIssues, ADCMApiError, BaseAPIListObject, BaseAPIObject, ObjectNotFound,
    TooManyArguments, WaitTimeout, strip_none_keys, min_server_version, allure_step,
    allure_attach_json, legacy_server_implementaion, EndPoint
)
from adcm_client.util import stream
from adcm_client.wrappers.api import ADCMApiWrapper

# Init logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class NoCredentionsProvided(Exception):
    """There is no user/password provided. It was not passed as init parameters
    during ADCMClient initialization and was not passed as a parameter to auth()
    function
    """


##################################################
#                 B U N D L E S
##################################################
class IncorrectPrototypeType(Exception):
    pass


class Bundle(BaseAPIObject):
    """The 'Bundle' object from the API"""
    IDNAME = "bundle_id"
    PATH = ["stack", "bundle"]
    FILTERS = ["name", "version"]
    id: int
    bundle_id: int
    name: Optional[str]
    description: Optional[str] = None
    version: Optional[str] = None
    edition: Optional[str] = None

    def __repr__(self):
        return f"<Bundle {self.name} {self.version} {self.edition} at {id(self)}>"

    def provider_prototype(self) -> "ProviderPrototype":
        """Return ProviderPrototype object"""
        return self._child_obj(ProviderPrototype)

    def provider_create(self, name, description=None) -> "Provider":
        """Creates Provider object from the prototype"""
        try:
            prototype = self.provider_prototype()
        except ObjectNotFound:
            raise IncorrectPrototypeType from None
        return prototype.provider_create(name, description)

    def provider_list(self, paging=None, **args) -> "ProviderList":
        """Return list of 'Provider' objects"""
        try:
            prototype = self.provider_prototype()
        except ObjectNotFound:
            raise IncorrectPrototypeType from None
        return prototype.provider_list(paging=paging, **args)

    def provider(self, **args) -> "Provider":
        """Return 'Provider' object from the 'ProviderPrototype' object"""
        try:
            prototype = self.provider_prototype()
        except ObjectNotFound:
            raise IncorrectPrototypeType from None
        return prototype.provider(**args)

    def service_prototype(self, **args) -> "ServicePrototype":
        """Return 'ServicePrototype' object"""
        return self._child_obj(ServicePrototype, **args)

    def cluster_prototype(self) -> "ClusterPrototype":
        """Return 'ClusterPrototype' object"""
        return self._child_obj(ClusterPrototype)

    def cluster_create(self, name, description=None) -> "Cluster":
        """Creates 'Cluster' object from the 'ClusterPrototype' object"""
        try:
            prototype = self.cluster_prototype()
        except ObjectNotFound:
            raise IncorrectPrototypeType from None
        return prototype.cluster_create(name, description)

    def cluster_list(self, paging=None, **args) -> "ClusterList":
        """Return list of 'Cluster' objects"""
        try:
            prototype = self.cluster_prototype()
        except ObjectNotFound:
            raise IncorrectPrototypeType from None
        return prototype.cluster_list(paging=paging, **args)

    def cluster(self, **args) -> "Cluster":
        """Return 'Cluster' object from the 'ClusterPrototype' object"""
        try:
            prototype = self.cluster_prototype()
        except ObjectNotFound:
            raise IncorrectPrototypeType from None
        return prototype.cluster(**args)

    def license(self):
        """Provide endpoint to licence/read"""
        return self._subcall("license", "read")

    def license_accept(self):
        """Provide endpoint to licence/accept/update"""
        self._subcall("license", "accept", "update")


class BundleList(BaseAPIListObject):
    """List of 'Bundle' object from the API"""
    _ENTRY_CLASS = Bundle


##################################################
#              P R O T O T Y P E
##################################################
class Prototype(BaseAPIObject):
    """The 'Prototype' object from the API"""
    PATH = ["stack", "prototype"]
    IDNAME = "prototype_id"
    FILTERS = ["name", "bundle_id"]

    id: Optional[int] = None
    prototype_id: Optional[int] = None
    name: Optional[str] = None
    type: Optional[str] = None
    description: Optional[str] = None
    version: Optional[str] = None
    bundle_id: Optional[int] = None
    config: Optional[dict] = None
    actions = None  # Need help with its type
    url: Optional[str] = None

    def bundle(self) -> "Bundle":
        """Return 'Bundle' object"""
        return self._parent_obj(Bundle)


class PrototypeList(BaseAPIListObject):
    """List of 'Prototype' object from the API"""
    _ENTRY_CLASS = Prototype


class ClusterPrototype(Prototype):
    """The 'ClusterPrototype' object from the API"""
    PATH = ["stack", "cluster"]
    FILTERS = ["name", "bundle_id"]

    def cluster_create(self, name, description=None) -> "Cluster":
        """Create 'Cluster' object with relevant parameters"""
        if self.type != 'cluster':
            raise IncorrectPrototypeType
        return new_cluster(
            self._api,
            prototype_id=self.prototype_id,
            name=name,
            description=description
        )

    def cluster_list(self, paging=None, **args) -> "ClusterList":
        """Return list of 'Cluster' objects"""
        return self._child_obj(ClusterList, paging=paging, **args)

    def cluster(self, **args) -> "Cluster":
        """Return 'Cluster' object"""
        return self._child_obj(Cluster, **args)


class ClusterPrototypeList(BaseAPIListObject):
    """List of 'ClysterPrototype' object from the API"""
    _ENTRY_CLASS = ClusterPrototype


class ServicePrototype(Prototype):
    """The 'ServicePrototype' object from the API"""
    PATH = ["stack", "service"]
    FILTERS = ["name", "bundle_id"]

    shared: Optional[bool] = None
    display_name: Optional[str] = None
    required: Optional[bool] = None
    components = None  # Need help with its type
    exports = None  # Need help with its type
    imports = None  # Need help with its type
    monitoring: Optional[str] = None
    path: Optional[str] = None
    bundle_edition: Optional[str] = None

    @min_server_version('2020.09.25.13')
    def service_list(self, paging=None, **args) -> "ServiceList":
        """Return list of 'Service' objects and check its minimal version"""
        return self._child_obj(ServiceList, paging=paging, **args)

    @min_server_version('2020.09.25.13')
    def service(self, **args) -> "Service":
        """Return 'Service' object and check its minimal version"""
        return self._child_obj(Service, **args)


class ServicePrototypeList(BaseAPIListObject):
    """List of 'ServicePrototype' object from the API"""
    _ENTRY_CLASS = ServicePrototype


class ProviderPrototype(Prototype):
    """The 'ProvidePrototype' object from the API"""
    PATH = ["stack", "provider"]
    FILTERS = ["name", "bundle_id"]

    display_name: Optional[str] = None
    required: Optional[bool] = None
    upgrade = None  # Need help with its type
    path: Optional[str] = None
    bundle_edition: Optional[str] = None
    license: Optional[str] = None

    def provider_create(self, name, description=None) -> "Provider":
        """Create 'Provider' object with relevant parameters"""
        if self.type != 'provider':
            raise IncorrectPrototypeType
        return new_provider(
            self._api,
            prototype_id=self.prototype_id,
            name=name,
            description=description
        )

    def provider_list(self, paging=None, **args) -> "ProviderList":
        """Return list of 'Provider' objects"""
        return self._child_obj(ProviderList, paging=paging, **args)

    def provider(self, **args) -> "Provider":
        """Return 'Provider' object"""
        return self._child_obj(Provider, **args)


class ProviderPrototypeList(BaseAPIListObject):
    """List of 'ProvidePrototype' object from the API"""
    _ENTRY_CLASS = ProviderPrototype


class HostPrototype(Prototype):
    """The 'HostPrototype' object from the API"""
    PATH = ["stack", "host"]
    FILTERS = ["name", "bundle_id"]

    display_name: Optional[str] = None
    required: Optional[bool] = None
    monitoring: Optional[str] = None
    path: Optional[str] = None
    bundle_edition: Optional[str] = None

    def host_list(self, paging=None, **args) -> "HostList":
        """Return list of 'Host' objects"""
        return self._child_obj(HostList, paging=paging, **args)

    def host(self, **args) -> "Host":
        """Return 'Host' object"""
        return self._child_obj(Host, **args)


class HostPrototypeList(BaseAPIListObject):
    """List of 'HostPrototype' objects from the API"""
    _ENTRY_CLASS = HostPrototype


##################################################
#           B A S E  O B J E C T
##################################################
class _BaseObject(BaseAPIObject):
    """
    Base class 'BaseObject' for adcm_client objects
    """
    id: Optional[int] = None
    url: Optional[str] = None
    state: Optional[str] = None
    prototype_id: Optional[int] = None
    issue: Optional[dict] = None
    button: Optional[str] = None

    def prototype(self):
        """Return Error if method or function hasn't implemented in derived class"""
        raise NotImplementedError

    def action(self, **args) -> "Action":
        """Return 'Action' object"""
        return self._subobject(Action, **args)

    def action_list(self, paging=None, **args) -> "ActionList":
        """Return list of 'Action' objects"""
        return self._subobject(ActionList, paging=paging, **args)

    def action_run(self, **args) -> "Task":
        """Run action which returns 'Task' object"""
        warnings.warn('Deprecated. The method accepts no arguments for the "action.run()" method.',
                      DeprecationWarning, stacklevel=2)
        action = self.action(**args)
        return action.run()

    def config(self, full=False):
        """Provide endpoint for config/current/list. If none current - returns config"""
        history_entry = self._subcall("config", "current", "list")
        if full:
            return history_entry
        return history_entry['config']

    @allure_step("Save config")
    def config_set(self, data):
        """Save completed config in history"""
        # this check is incomplete, cases of presence of keys "config" and "attr" in config
        # are not considered
        allure_attach_json(data, name="Complete config")
        if "config" in data and "attr" in data:
            if data["attr"] is None:
                data["attr"] = {}
            history_entry = self._subcall(
                'config', 'history', 'create', config=data['config'], attr=data['attr'])
            return {key: value for key, value in history_entry.items() if key in ['config', 'attr']}
        history_entry = self._subcall('config', 'history', 'create', config=data)
        return history_entry['config']

    @allure_step("Save config")
    def config_set_diff(self, data):
        """Save the difference between old and new config in history"""

        def update(d, u):
            """If the old and new values are dictionaries, we try to update, otherwise we replace"""
            for key, value in u.items():
                if isinstance(value, abc.Mapping) and key in d and isinstance(d[key], abc.Mapping):
                    d[key] = update(d[key], value)
                    continue
                d[key] = value
            return d

        # this check is incomplete, cases of presence of keys "config" and "attr" in config
        # are not considered
        allure_attach_json(data, name="Changed fields")
        is_full = "config" in data and "attr" in data
        config = self.config(full=is_full)
        allure_attach_json(config, name="Original config")
        return self.config_set(update(config, data))

    def config_prototype(self):
        return self.prototype().config


##################################################
#              P R O V I D E R
##################################################
class Provider(_BaseObject):
    """The 'Provider' object from the API"""
    IDNAME = "provider_id"
    PATH = ["provider"]
    FILTERS = ["name", "prototype_id"]
    provider_id: Optional[int] = None
    edition: Optional[str] = None
    license: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    bundle_id: Optional[int] = None

    def __repr__(self):
        return f"<Provider {self.name} at {id(self)}>"

    def bundle(self) -> "Bundle":
        """Return 'Bundle' object"""
        return self._parent_obj(Bundle)

    def host_create(self, fqdn) -> "Host":
        """Create new 'Host' object includes information about FQDN"""
        return new_host(self._api, **self._merge(fqdn=fqdn))

    def host_list(self, paging=None, **args) -> "HostList":
        """Return list of 'Host' objects"""
        return self._child_obj(HostList, paging=paging, **args)

    def host(self, **args) -> "Host":
        """Return 'Host' object"""
        return self._child_obj(Host, **args)

    def prototype(self) -> "ProviderPrototype":
        """Return 'ProviderPrototype' object"""
        return self._parent_obj(ProviderPrototype)

    def upgrade(self, **args) -> "Upgrade":
        """Return 'Upgrade' object"""
        return self._subobject(Upgrade, **args)

    def upgrade_list(self, paging=None, **args) -> "UpgradeList":
        """Return list of 'Upgrade' objects"""
        return self._subobject(UpgradeList, paging=paging, **args)


class ProviderList(BaseAPIListObject):
    """List of 'Provider' objects from the API"""
    _ENTRY_CLASS = Provider


@allure_step('Create provider {name}')
def new_provider(api, **args) -> "Provider":
    """Create new 'Provider' object"""
    p = api.objects.provider.create(**strip_none_keys(args))
    return Provider(api, provider_id=p['id'])


##################################################
#              C L U S T E R
##################################################
class Cluster(_BaseObject):
    """The 'Cluster' object from the API"""
    IDNAME = "cluster_id"
    PATH = ["cluster"]
    FILTERS = ["name", "prototype_id"]
    cluster_id: Optional[int] = None
    name: Optional[str] = None
    description: Optional[str] = None
    bundle_id: Optional[int] = None
    serviceprototype = None  # Need help with its type
    status: Optional[str] = None
    edition: Optional[str] = None
    license: Optional[str] = None

    def __repr__(self):
        return f"<Cluster {self.name} from bundle - {self.bundle_id} at {id(self)}>"

    def prototype(self) -> "ClusterPrototype":
        """Return 'ClusterPrototype' object as its prototype"""
        return self._parent_obj(ClusterPrototype)

    def bind(self, target):
        """Check target type. If it is cluster or service - provide matching endpoint"""
        if isinstance(target, Cluster):
            self._subcall("bind", "create", export_cluster_id=target.cluster_id)
        elif isinstance(target, Service):
            self._subcall("bind", "create", export_cluster_id=target.cluster_id,
                          export_service_id=target.service_id)
        else:
            raise NotImplementedError

    def bind_list(self, paging=None):
        """Provide endpoint to bind/list"""
        return self._subcall("bind", "list")

    def bundle(self) -> "Bundle":
        """Return 'Bundle' object from Cluster prototype"""
        proto = self.prototype()
        return proto.bundle()

    def button(self):
        """Return Error if method or function hasn't implemented in derived class"""
        raise NotImplementedError

    def host(self, **args) -> "Host":
        """Return 'Host' object"""
        return self._child_obj(Host, **args)

    def host_list(self, paging=None, **args) -> "HostList":
        """Return list of 'Host' objects"""
        return self._child_obj(HostList, paging=paging, **args)

    def host_add(self, host: "Host") -> "Host":
        """Create and add new 'Host' object to Cluster"""
        with allure_step(f"Add host {host.fqdn} to cluster {self.name}"):
            data = self._subcall("host", "create", host_id=host.id)
            return Host(self._api, id=data['id'])

    def host_delete(self, host: "Host"):
        """Delete 'Host' from Cluster"""
        with allure_step(f"Remove host {host.fqdn} from cluster {self.name}"):
            self._subcall("host", "delete", host_id=host.id)

    def _service_old(self, **args) -> "Service":
        """Return 'Service' object"""
        return self._subobject(Service, **args)

    # !!! If you change the version, do not forget to change it in the __new__ method
    # of the Service class as well as in the comments to them
    @legacy_server_implementaion(_service_old, '2020.09.25.13')
    def service(self, **args) -> "Service":
        """Return 'Service' object and check last version of service"""
        return self._child_obj(Service, **args)

    def _service_list_old(self, paging=None, **args) -> "ServiceList":
        """Return list of 'Service' objects"""
        return self._subobject(ServiceList, paging=paging, **args)

    # !!! If you change the version, do not forget to change it in the __new__ method
    # of the Service class as well as in the comments to them
    @legacy_server_implementaion(_service_list_old, '2020.09.25.13')
    def service_list(self, paging=None, **args) -> "ServiceList":
        """Return list of 'Service' objects"""
        return self._child_obj(ServiceList, paging=paging, **args)

    def _service_add_old(self, **args) -> "Service":
        """Add existed Service from prototype to cluster, return 'Service' object"""
        proto = self.bundle().service_prototype(**args)
        with allure_step(f"Add service {proto.name} to cluster {self.name}"):
            data = self._subcall("service", "create", prototype_id=proto.id)
            return self._subobject(Service, service_id=data['id'])

    # !!! If you change the version, do not forget to change it in the __new__ method
    # of the Service class as well as in the comments to them
    @legacy_server_implementaion(_service_add_old, '2020.09.25.13')
    def service_add(self, **args) -> "Service":
        """Add new Service from prototype to cluster, return 'Service' object"""
        proto = self.bundle().service_prototype(**args)
        with allure_step(f"Add service {proto.name} to cluster {self.name}"):
            data = self._subcall("service", "create", prototype_id=proto.id, cluster_id=self.id)
            return Service(self._api, id=data['id'])

    @min_server_version('2020.05.13.00')
    def service_delete(self, service: "Service"):
        """Delete service from cluster"""
        with allure_step(f"Remove service {service.name} from cluster {self.name}"):
            self._subcall("service", "delete", service_id=service.id)

    def hostcomponent(self):
        """Provide endpoint to hostcomponent/list"""
        return self._subcall("hostcomponent", "list")

    @allure_step("Save hostcomponents map")
    def hostcomponent_set(self, *hostcomponents):
        """Add readable and complete host components to JSON"""
        hc = []
        readable_hc = []
        for i in hostcomponents:
            h, c = i
            hc.append({
                'host_id': h.id,
                'service_id': c.service_id,
                'component_id': c.id
            })
            readable_hc.append({
                'host_fqdn': h.fqdn,
                'component_name': c.display_name
            })
        allure_attach_json(readable_hc, name="Readable hc map")
        allure_attach_json(hc, name="Complete hc map")
        return self._subcall("hostcomponent", "create", hc=hc)

    def status_url(self):
        """Provide endpoint to status/list"""
        return self._subcall("status", "list")

    def imports(self):
        """Provide endpoint to import/list"""
        return self._subcall("import", "list")

    def upgrade(self, **args) -> "Upgrade":
        """Return 'Upgrade' object"""
        return self._subobject(Upgrade, **args)

    def upgrade_list(self, paging=None, **args) -> "UpgradeList":
        """Return list of 'Upgrade' objects"""
        return self._subobject(UpgradeList, paging=paging, **args)


class ClusterList(BaseAPIListObject):
    """List of 'HostPrototype' objects from the API"""
    _ENTRY_CLASS = Cluster


@allure_step('Create cluster {name}')
def new_cluster(api: ADCMApiWrapper, **args) -> "Cluster":
    """Create new 'Cluster' object"""
    c = api.objects.cluster.create(**strip_none_keys(args))
    return Cluster(api, cluster_id=c['id'])


##################################################
#          U P G R A D E
##################################################
class Upgrade(BaseAPIObject):
    """The 'Upgrade' object from the API"""
    IDNAME = "upgrade_id"
    PATH = None
    SUBPATH = ["upgrade"]

    id: Optional[int] = None
    upgrade_id: Optional[int] = None
    bundle_id: Optional[int] = None
    license_url: Optional[str] = None
    url: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    min_version: Optional[str] = None
    max_version: Optional[str] = None
    min_strict: Optional[bool] = None
    max_strict: Optional[bool] = None
    upgradable: Optional[bool] = None
    state_available: Optional[list] = None
    state_on_success: Optional[str] = None
    from_edition: Optional[List[str]] = None

    def do(self, **args):
        """Do upgrade and provide do/create endpoint"""
        with allure_step(f"Do upgrade {self.name}"):
            self._subcall("do", "create", **args)


class UpgradeList(BaseAPIListObject):
    """List of 'Upgrade' objects from the API"""
    SUBPATH = ["upgrade"]
    _ENTRY_CLASS = Upgrade


##################################################
#           S E R V I C E S
##################################################
class Service(_BaseObject):
    """The 'Service' object from the API"""
    IDNAME = "service_id"
    PATH = ['service']
    SUBPATH = ['service']
    FILTERS = ['cluster_id']

    id: Optional[int] = None
    service_id: Optional[int] = None
    bundle_id: Optional[int] = None
    name: Optional[str] = None
    description: Optional[str] = None
    display_name: Optional[str] = None
    cluster_id: Optional[int] = None
    status: Optional[str] = None
    button: Optional[str] = None
    monitoring: Optional[str] = None

    def __new__(cls, *args, **kwargs):
        """
        Set PATH=None, if adcm version < `2020.09.25.13`. See ADCM-1439.
        This method is associated with the action of the `legacy_server_implementaion()` decorator.
        """
        wrapper = args[0]
        instance = super().__new__(cls)
        # !!! If you change the version, do not forget to change it in the service(), service_list()
        # and service_add() methods of the Cluster class as well as in the comments to them
        if rpm.compare_versions(wrapper.adcm_version, '2020.09.25.13') < 0:
            instance.PATH = None
        return instance

    def __repr__(self):
        return f"<Service {self.name} form cluster - {self.cluster_id} at {id(self)}>"

    def bind(self, target):
        """Check target type. If it is cluster or service - provide matching endpoint"""
        if isinstance(target, Cluster):
            self._subcall("bind", "create", export_cluster_id=target.cluster_id)
        elif isinstance(target, Service):
            self._subcall("bind", "create", export_cluster_id=target.cluster_id,
                          export_service_id=target.service_id)
        else:
            raise NotImplementedError

    def prototype(self) -> "ServicePrototype":
        """Return new 'ServicePrototype' object"""
        return ServicePrototype(self._api, id=self.prototype_id)

    def cluster(self) -> Cluster:
        """Return 'Cluster' object"""
        return Cluster(self._api, id=self.cluster_id)

    def imports(self):
        """Provide endpoint to import/list"""
        return self._subcall("import", "list")

    def bind_list(self, paging=None):
        """Provide endpoint bind/list"""
        return self._subcall("bind", "list")

    def _component_old(self, **args) -> "Component":
        """Return 'Component' object"""
        return self._subobject(Component, **args)

    # Set a real version when components feature will be merged into develop
    # https://github.com/arenadata/adcm/pull/778
    # !!! If you change the version, do not forget to change it in the __new__ method
    # of the Component class as well as in the comments to them
    @legacy_server_implementaion(_component_old, '2021.03.12.16')
    def component(self, **args) -> "Component":
        """
        Return 'Component' object according to the version
        (Return old version of func if version is older)
        """
        return self._child_obj(Component, **args)

    def _component_list_old(self, paging=None, **args) -> "ComponentList":
        """Return list of 'Component' objects"""
        return self._subobject(ComponentList, paging=paging, **args)

    # Set a real version when components feature will be merged into develop
    # https://github.com/arenadata/adcm/pull/778
    # !!! If you change the version, do not forget to change it in the __new__ method
    # of the Component class as well as in the comments to them
    @legacy_server_implementaion(_component_list_old, '2021.03.12.16')
    def component_list(self, paging=None, **args) -> "ComponentList":
        """
        Return list of 'Component' object according to the version
        (Return old version of func if version is older)
        """
        return self._child_obj(ComponentList, paging=paging, **args)


class ServiceList(BaseAPIListObject):
    """List of 'Service' objects from the API"""
    PATH = ['service']
    SUBPATH = ['service']
    _ENTRY_CLASS = Service

    def __new__(cls, *args, **kwargs):
        """
        Set PATH=None, if adcm version < `2020.09.25.13`. See ADCM-1439.
        This method is associated with the action of the `legacy_server_implementaion()` decorator.
        """
        wrapper = args[0]
        instance = super().__new__(cls)
        # !!! If you change the version, do not forget to change it in the service(), service_list()
        # and service_add() methods of the Cluster class as well as in the comments to them
        if rpm.compare_versions(wrapper.adcm_version, '2020.09.25.13') < 0:
            instance.PATH = None
        return instance


##################################################
#           C O M P O N E N T S
##################################################
class Component(_BaseObject):
    """The 'Component' object from the API"""
    IDNAME = "component_id"
    PATH = ["component"]
    SUBPATH = ["component"]

    id: Optional[int] = None
    component_id: Optional[int] = None
    cluster_id: Optional[int] = None
    _service_id: Optional[int] = None
    name: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    constraint: Optional[List[Union[int, str]]] = None
    params: Optional[dict] = None
    prototype_id: Optional[int] = None
    requires: Optional[list] = None
    bound_to: Optional[dict] = None
    monitoring: Optional[str] = None
    status: Optional[str] = None
    state: Optional[str] = None

    def __new__(cls, *args, **kwargs):
        """
        Set PATH=None, if adcm version < `2021.03.12.16`. See ADCM-1439.
        This method is associated with the action of the `legacy_server_implementaion()` decorator.
        """
        wrapper = args[0]
        instance = super().__new__(cls)
        # !!! If you change the version, do not forget to change it in the component()
        # and component_list() methods of the Service class as well as in the comments to them
        if rpm.compare_versions(wrapper.adcm_version, '2021.03.12.16') < 0:
            instance.PATH = None
        return instance

    @property
    def service_id(self):
        """Return {service_id} if it isn't None"""
        # this code is for backward compatibility
        if self._service_id is not None:
            return self._service_id
        try:
            return self._endpoint.path_args["service_id"]
        except KeyError:
            return self._data['service_id']

    @service_id.setter
    def service_id(self, value):
        """Set service_id as {value}"""
        self._service_id = value


class ComponentList(BaseAPIListObject):
    """List of 'Component' objects from the API"""
    PATH = ["component"]
    SUBPATH = ["component"]
    _ENTRY_CLASS = Component

    def __new__(cls, *args, **kwargs):
        """
        Set PATH=None, if adcm version < `2021.03.12.16`. See ADCM-1439.
        This method is associated with the action of the `legacy_server_implementaion()` decorator.
        """
        wrapper = args[0]
        instance = super().__new__(cls)
        # !!! If you change the version, do not forget to change it in the component()
        # and component_list() methods of the Service class as well as in the comments to them
        if rpm.compare_versions(wrapper.adcm_version, '2021.03.12.16') < 0:
            instance.PATH = None
        return instance


##################################################
#              H O S T
##################################################
class Host(_BaseObject):
    """The 'Host' object from the API"""
    IDNAME = "host_id"
    PATH = ["host"]
    FILTERS = ["fqdn", "prototype_id", "provider_id", "cluster_id"]

    id: Optional[int] = None
    host_id: Optional[int] = None
    fqdn: Optional[str] = None
    provider_id: Optional[int] = None
    cluster_id: Optional[int] = None
    description: Optional[str] = None
    bundle_id: Optional[int] = None
    status: Optional[str] = None

    def __repr__(self):
        return f"<Host {self.fqdn} form provider - {self.provider_id} at {id(self)}>"

    def provider(self) -> "Provider":
        """Return 'Provider' object"""
        return self._parent_obj(Provider)

    def cluster(self) -> "Cluster":
        """Return 'Cluster' object"""
        return self._parent_obj(Cluster)

    def bundle(self) -> "Bundle":
        """Return 'Bundle' object"""
        return self._parent_obj(Bundle)

    def prototype(self) -> "HostPrototype":
        """Return 'HostPrototype' object"""
        return self._parent_obj(HostPrototype)


class HostList(BaseAPIListObject):
    """List of 'Host' objects from the API"""
    _ENTRY_CLASS = Host


@allure_step('Create host {fqdn}')
def new_host(api, **args) -> "Host":
    """Create new 'Host' object and return it"""
    h = api.objects.provider.host.create(**args)
    return Host(api, host_id=h['id'])


##################################################
#              A C T I O N
##################################################
class Action(BaseAPIObject):
    """The 'Action' object from the API"""
    IDNAME = "action_id"
    PATH = None
    SUBPATH = ["action"]
    FILTERS = ["name"]

    action_id: Optional[int] = None
    button: Optional[str] = None
    id: Optional[int] = None
    name: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    params: Optional[dict] = None
    prototype_id: Optional[int] = None
    required_hostcomponentmap: Optional[list] = None
    hostcomponentmap: Optional[list] = None
    script: Optional[str] = None
    script_type: Optional[str] = None
    state_available: Optional[list] = None
    state_on_fail: Optional[str] = None
    state_on_success: Optional[str] = None
    type: Optional[str] = None
    url: Optional[str] = None
    subs: Optional[list] = None
    config: Optional[dict] = None
    ui_options: Optional[dict] = None
    allow_to_terminate: Optional[bool] = None
    partial_execution: Optional[bool] = None
    host_action: Optional[bool] = None

    def __repr__(self):
        return f"<Action {self.name} at {id(self)}>"

    def _get_config(self):
        config = dict()
        for item in self.config['config']:
            if item['type'] == 'group':
                config[item['name']] = dict()
            elif item['subname']:
                config[item['name']][item['subname']] = item['value']
            else:
                config[item['name']] = item['value']
        return config

    def log_files(self):
        raise NotImplementedError

    def task(self, **args) -> "Task":
        """Return 'Task' object"""
        return self._child_obj(Task, **args)

    def task_list(self, **args) -> "TaskList":
        """Return 'TaskList' object"""
        return self._child_obj(TaskList, **args)

    def run(self, **args) -> "Task":
        with allure_step(f"Run action {self.name}"):

            if 'hc' in args:
                allure_attach_json(args.get('hc'), name="Hostcomponent map")

            if 'config' in args and 'config_diff' in args:
                raise TypeError("only one argument is expected 'config' or 'config_diff'")

            if 'config' not in args:
                args['config'] = self._get_config()

                if 'config_diff' in args:
                    config_diff = args.pop('config_diff')
                    for item in self.config['config']:
                        if item['type'] == 'group':
                            continue

                        key, subkey = item['name'], item['subname']
                        if subkey and subkey in config_diff.get(key, {}):
                            args['config'][key][subkey] = config_diff[key][subkey]
                        elif not subkey and key in config_diff:
                            args['config'][key] = config_diff[key]
            # check backward compatibility for `verbose` option
            if rpm.compare_versions(self.adcm_version, '2021.02.04.13') >= 0:
                args.setdefault('verbose', False)
            elif 'verbose' in args:
                warnings.warn(f"ADCM {self.adcm_version} doesn't support action "
                              f"argument 'verbose'. It will be skipped")
                args.pop('verbose')
            try:
                data = self._subcall("run", "create", **args)
            except ErrorMessage as error:
                if (getattr(error.error, 'title', '') == '409 Conflict'
                        and 'has issues' in getattr(error.error, '_data', {}).get('desc', '')):
                    raise ActionHasIssues from error
                raise error
            return Task(self._api, task_id=data["id"])


class ActionList(BaseAPIListObject):
    """List of 'Action' objects from the API"""
    SUBPATH = ["action"]
    _ENTRY_CLASS = Action


##################################################
#              T A S K
##################################################
class TaskFailed(Exception):
    pass


TASK_PARENT = {
    'cluster': Cluster,
    'service': Service,
    'host': Host,
    'provider': Provider,
    'component': Component,
}


class Task(BaseAPIObject):
    """The 'Task' object from the API"""
    IDNAME = "task_id"
    PATH = ["task"]
    FILTERS = ['action_id', 'pid', 'status', 'start_date', 'finish_date']
    _END_STATUSES = ["failed", "success"]
    action_id: Optional[int] = None
    config: Optional[dict] = None
    hostcomponentmap: Optional[list] = None
    task_id: Optional[int] = None
    id: Optional[int] = None
    jobs: Optional[list] = None
    pid: Optional[int] = None
    selector = None
    status: Optional[str] = None
    url: Optional[str] = None
    object_id: Optional[int] = None
    object_type: Optional[str] = None

    @min_server_version('2020.08.27.00')
    def action(self) -> "Action":
        # for component object method will work after version `2021.03.12.16`
        kwargs = {f'{self.object_type}_id': self.object_id}
        return TASK_PARENT[self.object_type](
            self._api, **kwargs).action(action_id=self.action_id)

    def __repr__(self):
        return f"<Task {self.task_id} at {id(self)}>"

    def job(self, **args) -> "Job":
        """Return 'Job' object"""
        return Job(self._api, path_args=dict(task_id=self.id), **args)

    def job_list(self, paging=None, **args) -> "JobList":
        """Return list of 'Job' objects"""
        return JobList(self._api, paging=paging, path_args=dict(task_id=self.id), **args)

    @allure_step("Wait for task end")
    def wait(self, timeout=None, log_failed=True):
        try:
            status = self.wait_for_attr("status",
                                        self._END_STATUSES,
                                        timeout=timeout)
            if log_failed and status == "failed":
                self._log_jobs(status=status)
        except WaitTimeout as e:
            if log_failed:
                self._log_jobs()
            raise WaitTimeout from e
        return status

    @allure_step("Wait for the task to success")
    def try_wait(self, timeout=None):
        status = self.wait(timeout=timeout)

        if status == "failed":
            raise TaskFailed

        return status

    def _log_jobs(self, **filters):
        for job in self.job_list(**filters):
            log_func = logger.error if job.status == "failed" else logger.info
            try:
                action_name = self.action().name
            except ErrorMessage:
                action = EndPoint(self._api, 'action_id', ['stack', 'action']).read(self.action_id)
                action_name = action['name']
            log_func("Action: %s", action_name)
            for file in job.log_files:
                try:
                    response = self._api.client.get(file["url"])
                except ErrorMessage as error:
                    # pylint: disable=protected-access
                    if error.error._data['code'] == 'LOG_NOT_FOUND':
                        # pylint: enable=protected-access
                        continue
                    raise error
                content_format = response.get("format", "txt")
                if "type" in response:
                    log_func("Type: %s", response['type'])
                if "content" in response:
                    if content_format == "json":
                        log_func(dumps(response["content"], indent=2))
                    else:
                        log_func(response["content"])


class TaskList(BaseAPIListObject):
    """List of 'Task' objects from the API"""
    _ENTRY_CLASS = Task


##################################################
#              L O G
##################################################
class Log(BaseAPIObject):
    """The 'Log' object from the API"""
    IDNAME = 'log_id'
    PATH = ['job', 'log']
    SUBPATH = ['log']
    id: Optional[int] = None
    name: Optional[str] = None
    type: Optional[str] = None
    format: Optional[str] = None
    content = None  # Need help with its type


class LogList(BaseAPIListObject):
    """List of 'Log' objects from the API"""
    _ENTRY_CLASS = Log
    SUBPATH = ['log']


##################################################
#              J O B
##################################################
class Job(BaseAPIObject):
    """The 'Job' object from the API"""
    IDNAME = "job_id"
    PATH = ["job"]
    FILTERS = ['action_id', 'task_id', 'pid', 'status', 'start_date', 'finish_date']
    _END_STATUSES = ["failed", "success"]
    _WAIT_INTERVAL = .2
    id: Optional[int] = None
    job_id: Optional[int] = None
    pid: Optional[int] = None
    status: Optional[str] = None
    url: Optional[str] = None
    log_files: Optional[list] = None
    task_id: Optional[int] = None
    display_name: Optional[str] = None
    start_date: datetime = None
    finish_date: datetime = None

    def __repr__(self):
        return f"<Job {self.job_id} at {id(self)}>"

    # FIXME: remove method __init__, deal with argument path_args
    def __init__(self, api: ADCMApiWrapper, path=None, path_args=None, **args):
        super().__init__(api, path, **args)

    def task(self) -> "Task":
        """Return 'Task' object"""
        return self._parent_obj(Task)

    def wait(self, timeout=None):
        """Wait for the time ={timeout}"""
        return self.wait_for_attr("status",
                                  self._END_STATUSES,
                                  timeout=timeout)

    def log(self, **kwargs) -> "Log":
        """Return 'Log' object"""
        return self._subobject(Log, **kwargs)

    def log_list(self, paging=None, **kwargs) -> "LogList":
        """Return list of 'Log' objects"""
        return self._subobject(LogList, paging=paging, **kwargs)


class JobList(BaseAPIListObject):
    """List of 'Job' objects from the API"""
    _ENTRY_CLASS = Job


##################################################
#              A D C M
##################################################
class ADCM(_BaseObject):
    IDNAME = "adcm_id"
    PATH = ["adcm"]
    id: Optional[int] = None
    name: Optional[str] = None
    prototype_id: Optional[int] = None
    url: Optional[str] = None
    prototype_version: Optional[str] = None
    bundle_id: Optional[int] = None

    def prototype(self) -> "Prototype":
        """Return 'Prototype' object with id={prototype_id}"""
        return Prototype(self._api, id=self.prototype_id)


##################################################
#              C L I E N T
##################################################
class ADCMClient:
    _MIN_VERSION = "2019.02.20.00"

    def __init__(self, api=None, url=None, user=None, password=None):
        if api is not None:
            self._api = api
            self.url = api.url
            if self.api_token() is None:
                self.auth(user, password)
        else:
            self.url = url
            self._api = ADCMApiWrapper(self.url)
            self.auth(user, password)

        if self.api_token() is not None:
            self.guess_adcm_url()

        self.adcm_version = self._api.adcm_version
        self._check_min_version()

    def __repr__(self):
        return f"<ADCM API Client for {self.url} at {id(self)}>"

    @allure_step("Login to ADCM API with user={user} and password={password}")
    def auth(self, user=None, password=None):
        """Login to ADCM API with user={user} and password={password}"""
        if user is None or password is None:
            raise NoCredentionsProvided
        self._api.auth(user, password)
        if self.api_token() is None:
            raise ADCMApiError("Incorrect user/password. Unable to auth.")
        self._check_min_version()

    def reread(self):
        self._api.fetch()
        self.adcm_version = self._api.adcm_version

    def reset(self, api=None, url=None, user=None, password=None):
        """Re-init object. Useful in tests"""
        self.__init__(api=api, url=url, user=user, password=password)

    def _check_min_version(self):
        """Check client version and provide information about newer version"""
        if rpm.compare_versions(self._MIN_VERSION, self._api.adcm_version) > -1:
            raise ADCMApiError(
                "The client supports ADCM versions newer than '{}'".format(self._MIN_VERSION)
            )

    def api_token(self):
        return self._api.api_token

    def adcm(self) -> ADCM:
        """Return 'ADCM' object"""
        return ADCM(self._api)

    def guess_adcm_url(self):
        config = self.adcm().config()
        if config['global']['adcm_url'] is None:
            self.adcm().config_set_diff({"global": {"adcm_url": self.url}})

    def bundle(self, **args) -> Bundle:
        """Return 'Bundle' object"""
        return Bundle(self._api, **args)

    def bundle_list(self, paging=None, **args) -> BundleList:
        """Return list of 'Bundle' objects"""
        return BundleList(self._api, paging=paging, **args)

    def cluster(self, **args) -> Cluster:
        """Return 'Cluster' object"""
        return Cluster(self._api, **args)

    def cluster_list(self, paging=None, **args) -> ClusterList:
        """Return list of 'Cluster' objects"""
        return ClusterList(self._api, paging=paging, **args)

    def cluster_prototype(self, **args) -> ClusterPrototype:
        """Return 'ClusterPrototype' object"""
        return ClusterPrototype(self._api, **args)

    def cluster_prototype_list(self, paging=None, **args) -> ClusterPrototypeList:
        """Return list of 'ClusterPrototype' objects"""
        return ClusterPrototypeList(self._api, paging=paging, **args)

    def host(self, **args) -> Host:
        """Return 'Host' object"""
        return Host(self._api, **args)

    def host_list(self, paging=None, **args) -> HostList:
        """Return list of 'Host' objects"""
        return HostList(self._api, paging=paging, **args)

    def host_prototype(self, **args) -> HostPrototype:
        """Return 'HostPrototype' object"""
        return HostPrototype(self._api, **args)

    def host_prototype_list(self, paging=None, **args) -> HostPrototypeList:
        """Return list of 'HostPrototype' objects"""
        return HostPrototypeList(self._api, paging=paging, **args)

    def job(self, **args) -> Job:
        """Return 'Job' object"""
        return Job(self._api, **args)

    def job_list(self, paging=None, **args) -> JobList:
        """Return list of 'Job' objects"""
        return JobList(self._api, paging=paging, **args)

    def prototype(self, **args) -> Prototype:
        """Return 'Prototype' object"""
        return Prototype(self._api, **args)

    def prototype_list(self, paging=None, **args) -> PrototypeList:
        """Return list of 'Prototype' objects"""
        return PrototypeList(self._api, paging=paging, **args)

    def provider(self, **args) -> Provider:
        """Return 'Provider' object"""
        return Provider(self._api, **args)

    def provider_list(self, paging=None, **args) -> ProviderList:
        """Return list of 'Provider' objects"""
        return ProviderList(self._api, paging=paging, **args)

    def provider_prototype(self, **args) -> ProviderPrototype:
        """Return 'ProviderPrototype' object"""
        return ProviderPrototype(self._api, **args)

    def provider_prototype_list(self, paging=None, **args) -> ProviderPrototypeList:
        """Return list of 'ProviderPrototype' objects"""
        return ProviderPrototypeList(self._api, paging=paging, **args)

    def service(self, **args) -> Service:
        """Return 'Service' object"""
        return Service(self._api, **args)

    def service_prototype(self, **args) -> ServicePrototype:
        """Return 'ServicePrototype' object"""
        return ServicePrototype(self._api, **args)

    def service_prototype_list(self, paging=None, **args) -> ServicePrototypeList:
        """Return list of 'ServicePrototype' objects"""
        return ServicePrototypeList(self._api, paging=paging, **args)

    def _upload(self, bundle_stream) -> Bundle:
        """Upload and create Bundle from file={bundle_stream}"""
        self._api.objects.stack.upload.create(file=bundle_stream)
        data = self._api.objects.stack.load.create(bundle_file="file")
        return self.bundle(bundle_id=data['id'])

    @allure_step('Upload bundle from {dirname}')
    def upload_from_fs(self, dirname, **args) -> Bundle:
        """Upload single bundle from {dirname}"""
        streams = stream.file(dirname, **args)
        if len(streams) > 1:
            raise TooManyArguments('upload_bundle_from_fs is not capable with building multiple \
                bundle editions from one dir. Use upload_from_fs_all instead.')
        return self._upload(streams[0])

    @allure_step('Upload bundles from {dirname}')
    def upload_from_fs_all(self, dirname, **args) -> BundleList:
        """
        Upload multiple bundles from {dirname}
        """
        streams = stream.file(dirname, **args)
        result = BundleList(self._api, empty_bundlelist='not_existing_bundle')
        for st in streams:
            result.append(self._upload(st))
        return result

    @allure_step('Upload bundle from {url}')
    def upload_from_url(self, url) -> Bundle:
        """Upload bundle from {url}"""
        return self._upload(stream.web(url))

    def bundle_delete(self, **args):
        """Delete bundle object"""
        bundle = self.bundle(**args)
        with allure_step(f"Delete bundle {bundle.name}"):
            self._api.objects.stack.bundle.delete(bundle_id=bundle.bundle_id)
