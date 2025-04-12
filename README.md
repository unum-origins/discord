# discord

# Requirements

- A Mac (Linux will work too but you're on your own)
- make (I think comes with xcode, git, etc)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [kubectx](https://formulae.brew.sh/formula/kubectx)
- [kustomize](https://formulae.brew.sh/formula/kustomize)
- [Tilt](https://docs.tilt.dev/install.html)

# Install

To install as a module, list in requirements.txt as:

```
git+ssh://git@github.com.com/get-better-io/ledger.git@0.1.0#egg=ledger
```

# Development

If you make changes to `api/lib/ledger.py` make sure you bump the version in `VERSION`.

After merging to main, update locally and type `make tag` and that'll tag with the new version.

## Actions

Make sure you've installed:

Also make sure you have https://github.com/unum-pillars/mysql up and running.

- `make up` - Fires up Tilt (run locally in Kuberentes). Hit space to open the dashboard in a browser
  - In the browser, if any micorservices (blocks) fail (turn red/yellow) click the refresh in the block
- `make down` - Removes everything locally from Kuberentes
- `make setup` - Verifies that this repo can be installeeld as a module by other services
- `make tag` - Tags this repo because you're absolutely sure this is perfect and will work
- `make untag` - Undoes the taggin you just did because you totally screwed something up

## Directories / Files

- `Makefile` - File that provides all the `make` commands
- `Tiltfile` - Deploys to the locally Kubernetes environment
- `kubernetes/` - Service Kubernetes files
  - `base/` - Base kustomization for the service to deploy to production
    - `namespace.yaml` - Namespace file
    - `kustomization.yaml` - Collates the above
  - `tilt/` - Tilt kustomization for the service to deploy locally
    - `kustomization.yaml` - Collates the base and microservice tilt kustomizations
- `.vscode/` - Settings for vscode local development and debugging
  - `lauch.json` - Debugger information for each microservice
- `secret/` - Directory used to create local secrets (.gitignore'd)
  - `mysql.json` - Connection informatioin for tilt-mysql
- `config/` - Directory used to create local config (.gitignore'd)
- `setup.py` - Makes this repo installable as `pip install git@github.com.com:get-better-io/ledger.git` to access these Models via this API

# discord-daemon

## Actions

- `cd daemon` - Enter this microservice
- `make dep` - Pull dependencies from api (do this first)
- `make build` - Build a local image to use
- `make test` - Run tests
- `make debug` - Run tests with step through debugging. Will pause until the 'daemon' debugger is started.
- `make shell` - Fire up a shell for deeper testing / debugging
  - `$test test.test_service` - Test only the `test/test_service.py` file
  - `$test test.test_service.TestHealth` - Test only the `test/test_service.py` `TestHealth` class
  - `$test test.test_service.TestHealth.test_get` - Test only the `test/test_service.py` `TestHealth.test_get` method
  - `$debug test.test_service` - Debug only the `test/test_service.py` file
  - `$debug test.test_service.TestHealth` - Debug only the `test/test_service.py` `TestHealth` class
  - `$debug test.test_service.TestHealth.test_get` - Debug only the `test/test_service.py` `TestHealth.test_get` method
  - Make sure you fire up the debugger for those above
- `make lint`- Run the linter (uses `.pylintc`)

## Directories / Files

- `Makefile` - File that provides all the `make` commands
- `Dockerfile` - File that builds the Docker image
- `requirements.txt` - Put all your standard Python libs here
- `.pylintrc` - L:inting definitions. Change to suit your needs.
- `bin/` - Executables
  - `daemon.py` - Runs the daemon
- `kubernetes/` - Kubernetes files
  - `base/` - Base files, what's deploy to the actual cluster
    - `daemon.yaml` - Deployment and Service for daemon
    - `prometheus.yaml` - Prometheus Monitors
    - `kustomization.yaml` - Collates the above to form base
  - `tilt/` - Tilt files, what's deploy to your local machine
    - `daemon.yaml` - Deployment and Service for daemon overriden for debugging
    - `kustomization.yaml` - Collates the above to form tilt
- `lib/` - Main code
  - `service.py` - Main daemon codes, etc.
- `test/` - Main code
  - `test_service.py` - Test daemon code, etc. Change to match your service changes
