# OpI toolkit charm for Juju configuration autowiring

"The OpI Charm is king"

## What is this?
This is a demo charm to show the configuration autowiring functionality of the `OpI` Juju charm library. The library automatically wires changes to [juju relations](https://juju.is/docs/sdk/relations) into your charmed application's configuration files.

## How do I run the example?
To run this charm and see it working, follow the steps below:

```sh
# install the stuff
snap install juju --classic
snap install charmcraft
snap install microk8s --classic
sudo usermod -aG microk8s $(whoami)
su - $(whoami)
microk8s status --wait-ready
microk8s enable dns storage
juju bootstrap microk8s micro
juju add-model testing
# get this code
git clone https://github.com:grobbie/mongo-gui-operator.git
mv mongo-gui-operator opi
pushd opi
charmcraft build
juju deploy ./opi.charm --resource application-image=ubuntu:20.04
popd
# set up Mongodb
git clone https://github.com/balbirthomas/mongodb-operator.git
pushd mongodb-operator
charmcraft build
juju deploy ./mongodb.charm --resource mongodb-image=mongo:4.4.1
popd
pushd opi
microk8s.kubectl logs opi-0 -c charm
# check the charm is initialised. When it is, you should see output like:
## starting containeragent unit command
## containeragent unit "unit-opi-0" start (2.9.3 [gc])

# add a relation between our opi charm and mongodb
juju add-relation opi mongodb
microk8s.kubectl exec opi-0 -n testing -c opi -- cat /opt/opi/mongo-gui.sh
# you should see a config file with sensible relation output:
## MONGO_URL=mongodb://mongodb-0.mongodb-endpoints:27017/
microk8s.kubectl port-forward -n testing opi-0 4321:4321
# see a freeware mongodb database management UI
firefox http://localhost:4321/
# awesome.
popd
```

# How do I use it?
Currently you have to put the parameters you want to autoconfigure in a file in `$CHARM_ROOT/conf/config_files.yaml`

```yaml
- relation: <the relation name>
  property_name: <the property you want autoconfigured>
  property_value: <the default value for the property>
  template_file: <the filename of the jinja2 template>
  config_file_destination: </path/to/target/config_file.conf>
```

You can have many repeating blocks, one for each parameter you want to autoconfigure. You can include the same parameter multiple times, in order to set it in multiple configuration files.

You need to have templates for the configuration files in `$CHARM_ROOT/templates`. The templates need to respect jinja2 template file syntax and will receive a dictionary called `config`, which contains all of your parameters. Example:

```jinja
MONGO_URL={{ config["replica_set_uri"] }}
```

You'll need your charm to inherit from the `OpI` library class `ContentBase`:

```python
# import ContentBase
from charmlib.ContentBase import ContentBase
...

class DemoCharm(ContentBase): # your charm must inherit from ContentBase

  def __init__(self, *args):
    super().__init__(*args)

    # your charm needs to handle this event:
    self.evt_config_changed += self._on_config_rewritten

  def _on_config_rewritten(self, sender, eargs):
    # reload or restart your app in here
    ...
```
That's it, nothing else to do!
