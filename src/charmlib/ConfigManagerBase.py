#    Copyright 2021 Canonical, Ltd.
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
import os
import logging
import json
import pandas
import re
import yaml

from ops.charm import CharmBase
from ops.framework import StoredState
from jinja2 import Template
from jinja2.filters import FILTERS, environmentfilter
from pandas import DataFrame

logger = logging.getLogger(__name__)

class ConfigManagerBase(CharmBase):

    _cb_stored = StoredState()
    _config_changed = False
    _service_name = ""

    def charm_dir(self):
        """Return the root directory of the current charm"""
        d = os.environ.get('JUJU_CHARM_DIR')
        if d is not None:
            return d
        return os.environ.get('CHARM_DIR')

    def __init__(self, *args, service_name):
        """CTOR"""
        super().__init__(*args)

        self._service_name = service_name

        # read in properties to watch. StoredState can only handle simple types,
        # so first convert the YAML to a DataFrame and then serialize the DataFrame to JSON
        try:
            configs = pandas.json_normalize(yaml.safe_load(
                open(os.path.join(self.charm_dir(), 'conf/config_files.yaml')))).to_json()
            self._cb_stored.set_default(config_files=configs)
        except Exception as e:
            # no properties were defined, no event watchers will be set
            logger.error("ContentLib configuration file conf/config_files.json "
                         "was not found or misconfigured: {0}".format(str(e)))
            empty = DataFrame(columns=["relation", "property_name", "property_value", "template_file",
                                       "config_file_destination"]).to_json()
            self._cb_stored.set_default(config_files=empty)
            return

        bound_events = self.on.events()
        for ev in bound_events:
            if "relation_changed" in ev:
                self.framework.observe(self.on.events().get(
                    ev), self._contentlib_on_relation_changed)

    @environmentfilter
    def regex_replace(environment, s, find, replace):
        """Jinja2 custom function. 
        This one implements regular expression based replace"""
        try:
            pattern = re.compile(find)
            return pattern.sub(replace, s)
        except Exception as e:
            logger.error("failed to process regex: {0}".format(str(e)))
            return s

    FILTERS["regex_replace"] = regex_replace

    def _regenerate_config(self, config_files: DataFrame):
        """This method regenerates the application configuration files"""
        for index, config_file in config_files.iterrows():
            # first, find all properties for the config file in stored state
            cb_stored = pandas.read_json(self._cb_stored.config_files)
            all_properties = cb_stored[cb_stored["relation"].eq(
                config_file["relation"])]
            props = dict()
            for index, property in all_properties.iterrows():
                props[property["property_name"]] = property["property_value"]
            props_json = json.dumps(props)
            tf = config_file["template_file"]
            file = open(os.path.join(self.charm_dir(),
                        "templates/{0}".format(tf)), 'r')
            t = Template(file.read())
            configured_file = t.render(config=props)
            container = self.unit.get_container(self.service_name)
            container.push(config_file["config_file_destination"],
                           configured_file, make_dirs=True, permissions=0o755)

    def _contentlib_on_relation_changed(self, event):
        """This method is run when a watched relation changed event fires"""
        # identify config files affected by the relation
        cb_stored = pandas.read_json(self._cb_stored.config_files)
        for key in event.relation.data[event.unit]:
            # search the config_files dictionary for the relation and config variable,
            # then update it in the stored state,
            # then trigger a regeneration of the config file
            # repeat for all affected config files
            subset = cb_stored[cb_stored["relation"].eq(event.relation.name)]
            subset = subset[subset["property_name"].eq(key)]
            if subset["property_name"].count() > 0:
                for index, config_file in subset.iterrows():
                    # update the stored state for the given property
                    subset.at[index, "property_value"] = event.relation.data[event.unit].get(
                        key)
                    cb_stored.update(subset)
                    self._cb_stored.config_files = cb_stored.to_json()
                    # do stuff to regenerate the associated configuration file
                    self._regenerate_config(cb_stored)
                    # notify the workload it should restart or refresh itself
                    self._config_changed = True
        if self._config_changed:
            self._cb_stored.config_files = cb_stored.to_json()
            container = self.unit.get_container(self.service_name)
            if container.get_service(self.service_name).is_running():
                container.stop(self.service_name)
            container.start(self.service_name)

    def getconfig_changed(self):
        config_changed = self._config_changed
        if self._config_changed:
            self._config_changed = False
        return config_changed

    config_changed = property(getconfig_changed)

    def getservice_name(self):
        return self._service_name

    def setservice_name(self, service_name):
        self._service_name = service_name

    service_name = property(getservice_name)
