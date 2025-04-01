# ledger

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

Also make sure you have https://github.com/gaf3/tilt-mysql and https://github.com/gaf3/tilt-prometheus up and running.

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

# ledger-api

## Actions

- `cd api` - Enter this microservice
- `make ddl` - Create DDL statements from models
- `make build` - Build a local image to use
- `make test` - Run tests
- `make debug` - Run tests with step through debugging. Will pause until the 'api' debugger is started.
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
  - `api.py` - Runs the api for Tilt
  - `ddl.py` - Generates the DDL statements.
  - `migrate.py` - Applies migrations to the database
- `kubernetes/` - Kubernetes files
  - `base/` - Base files, what's deploy to the actual cluster
    - `api.yaml` - Deployment and Service for api
    - `prometheus.yaml` - Prometheus Monitors
    - `kustomization.yaml` - Collates the above to form base
  - `tilt/` - Tilt files, what's deploy to your local machine
    - `api.yaml` - Deployment and Service for api overriden for debugging
    - `kustomization.yaml` - Collates the above to form tilt
- `lib/` - Main code
  - `ledger.py` - Models, change these to your own
  - `service.py` - Main api code, endpoints, etc. Change Resource to match your models
- `test/` - Main code
  - `test_service.py` - Test api code, endpoints, etc. Change to match your service changes
- `mysql.sh` - Shell script that waits for MySQL to be ready

# ledger-gui

## Actions

- `cd gui` - Enter this microservice (do this first)
- `make build` - Build a local image to use (do this third)
- `make shell` - Fire up a shell for deeper testing / debugging

## Directories / Files

- `Makefile` - File that provides all the `make` commands
- `Dockerfile` - File that builds the Docker image
- `kubernetes/` - Kubernetes files
  - `base/` - Base files, what's deploy to the actual cluster
    - `gui.yaml` - Deployment and Service for gui
    - `prometheus.yaml` - Prometheus Monitors
    - `kustomization.yaml` - Collates the above to form base
  - `tilt/` - Tilt files, what's deploy to your local machine
    - `gui.yaml` - Deployment and Service for gui overriden for debugging
    - `kustomization.yaml` - Collates the above to form tilt
- `nginx/` - Nginx configuration
  - `nginx.conf` - OVerall config for nginx
  - `default.conf` - Reverse proxy to talk to api
- `www/` - Main code
  - `css/service.css` - Put customizations here
  - `js/relations.js` - Main Relations Controller.
  - `js/service.js` - Custom Controllers. This is were you changes go for new models
  - `index.html` - Only page loaded directly by the browser
  - `header.html` - Partial template for the header for all pages
  - `footer.html` - Partial template for the footer of all pages
  - `form.html` - Psrtial tempalte for all the pages with fields (create, retrieve, update)
  - `html.html` - Home template
  - `fields.html` - Sub template for for all the pages with fields (create, retrieve, update)
  - `create.html` - Create tempalte for all models
  - `retrieve.html` - Retrieve template for all models
  - `list.html`- List template for all models

# ledger-daemon

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

# ledger-cron

## Actions

- `cd cron` - Enter this microservice
- `make dep` - Pull dependencies from api (do this first)
- `make build` - Build a local image to use
- `make test` - Run tests
- `make debug` - Run tests with step through debugging. Will pause until the 'cron' debugger is started.
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
  - `cron.py` - Runs the cron
- `kubernetes/` - Kubernetes files
  - `base/` - Base files, what's deploy to the actual cluster
    - `cron.yaml` - Deployment and Service for cron
    - `prometheus.yaml` - Prometheus Monitors
    - `kustomization.yaml` - Collates the above to form base
  - `tilt/` - Tilt files, what's deploy to your local machine
    - `cron.yaml` - Deployment and Service for cron overriden for debugging
    - `kustomization.yaml` - Collates the above to form tilt
- `lib/` - Main code
  - `service.py` - Main cron codes, etc.
- `test/` - Main code
  - `test_service.py` - Test cron code, etc. Change to match your service changes
