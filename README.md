BlendNet
========

Blender network rendering farm system with dynamic allocating of required resources.

* [Site page about it](https://www.state-of-the-art.io/projects/blendnet/)

## Usage

Please check out the wiki page: [Wiki](https://github.com/state-of-the-art/BlendNet/wiki)

## Requirements

* Blender 2.80 - as a host for the Addon
* If you have a plan to use a cloud provider:
    * Google Cloud Platform (GCP)
        * Installed `Google Cloud SDK`
        * Existing project with activated compute api
        * gcloud credentials (user or service account)
        * Quotas ready to run planned amount of resources

## Purpose

Existing blender addons, that enabling network rendering on a cluster of instances
are too complicated, not enough automated or too expensive. The solution is just
to use the existing cloud providers with their cheap preemptible instances costs
~3 times less than the regular ones.

For example `GCP` n1-highcpu-64 (**64 core 57.6GB RAM**) will cost you just
**$0.48 per hour**. Just imagine this - a quite complicated `Cycles engine` frame
will cost just $0.50.

## Challenges

But yeah, it's not easy - preemptible instances are quite unstable and usually could
be terminated without any notification by the GCP engine in any minute. So we need a
system that will allow us to make sure that:

1. We can easily run a number new instances by clicking just one button in blender
2. When the instance is terminated, we will not lose the render results
3. It's cost-effective - the instances should live no more than required
    * When rendering is done - terminate the instances automatically
    * Unavailable timeout - that will automatically stop the worker if it's not
    pinged by controller for a certain amount of time
    * Resources are used near 100% to be sure we getting maximum for the money
    * Calculation of costs for user
4. Communication are secured (HTTPS and basic auth will work here)
5. API of system is simple and available for anyone (for further support/adjustments)

## Structure

* Protocol: HTTPS REST - easily accessible and could provide enough security
* Components:
    * Blender addon - interface simplifies user interaction and scheduling the jobs
    * Manager - controlling the resources, managing jobs and watching on status
    * Agent - individual worker with some processing powers

All the components could be used independently with a browser or curl.

### Blender Addon

It's integrated with the current Blender render engine and allow user to send the
same configuration to the Manager to use the cloud resources for rendering.

Area of responsibility:
* User UI with a way to configure and monitor the BlendNet activity.
* Creating the Manager instance and watch its status.
* Specifies tasks (one per frame) and upload the required dependencies for them.
* Restore connection on restart - so it's possible to retrieve the results.
* Shows the rendering process with detailed status and previews.

It's also making sure, that the project contains all the required dependencies, like
textures, caches, physic bakes and so on - Agents will render just one frame, so it
should already contain all the required caches before starting to render.

### Manager

Required to make sure - even if blender will be closed, the rendering process will
be continued and the results will not be lost. Will execute the tasks sequentially -
if the current task is almost complete and have waiting resources, it will start the
next one to load the resources as much as possible.

Area of responsibility:
* Allocating resources according the task specification.
* Manages the allocated resources (if some resources going offline - restores it).
* Planning the load (resources should work, not wait for dependencies).
* Collects and merges the previews and results from the Agents.
* Saving your money as much as possible.

When a task is marked to execute - manager starting it and preparing a plan: it needs
to create the Agents, determine the number of samples per agent, upload the
dependencies to them, run the execution and watch for the status and progress.
Meanwhile, it should plan for the next task (if there are some) - preload the
dependencies and put it on hold.

It will leave the agents active for a short period of time after the rendering process
(by default 5 mins), will stop them after that. It will delete agents and stop itself
if there is no tasks for 30 mins (by default).

Tasks are coming from Addon: one task - one frame. Task have a number of samples to
render - and manager decides how much samples it will give to an agent. The Manager
tries to keep the ratio loading/rendering relatively lower, but less than 30 mins per
agent task. By default it's 100 samples per agent task.

#### Security

The Manager can control instances (Agents) in the project, can write/read to/from the
project buckets and have an external IP. All the connections are encrypted and access
is protected by a strong generated password, but it's a good idea to stop the instance
when it's not needed anymore (by default timeout is set to 30 mins).

### Agent

Main workhorse of the system - receiving task, dependencies, configs and start working
on it. Reports status and previews back - so Manager (and user) could watch on
progress.

Area of responsibility:
* Receives granular task from the manager with all the dependencies.
* Executes the rendering process with verbose reports of the status.
* Captures periodic previews to show the preliminary results.
* Captures render result.
* Watching on self-health status - if going to shutdown, captures the render result.

#### Security

The Agent has an external IP for a short period of time to get the required blender
dependencies - after that it's removed by the Manager. All the connections are
encrypted and access is protected by a strong generated password.

## Protection

Since we don't want anyone but us to see our information or use our resources -
BlendNet provides 2 simple protection mechanisms: BasicAuth and TLS.

### Basic Auth

Is a simple HTTP mechanism to make sure the only one have the right credentials can
access the server resources. During Manager setup Addon generates (or use preset) pair
of user/password - they are stored as Manager configuration.

When Addon want to talk with Manager - it provides credentials in the HTTP request
header, Manager compares those creds with the stored ones and if they are ok - allow
the request and respond.

Almost the same process happening between Manager and Agent - but with agent
credentials.

Those credentials are passed to the Manager/Agent as clear text, so BlendNet using TLS
to encrypt the whole communication between client and server.

### TLS

Required to encrypt the message transport - so no one but client and server can read
those messages during transmission. That means any communication or transfer between
Addon & Manager or Manager and Agent is completely encrypted.

TLS using asymmetric encryption that involves 2 keys - private and public. In case of
TLS public key file is also contains some readable information and called certificate.

When Manager is created the first time - it generates a custom Certificate Authority
certificate and signing all the generated certificates with this CA certificate.
Manager uploads this certificate back to the bucket and Addon can use it to confirm
that this manager is the one Addon need.

When Manager creates Agents - it generates certificates for each one and use CA to
confirm the identity of the agents.

## Pipeline

Blender `Addon` getting the required credentials to run instances on providers (`GCP`
and `local` is planned, later the other providers could be added). User also configures
some settings for the providers - what kind of instances he would like to use, timeouts
and cost limits. Also, it checks for the proper setup of the project - make sure quotas
and permissions are setup correctly.

When user choosing to start task - addon saving a temporary blend file and creating
the `Manager` (locally or on the provider instance - depends on user choice). It's
passing the blend file, resources, local baked caches and a task specification to work
on.

`Manager` allocates the required resources and start the `Agent` workers. Splitting the
task into a number of tasks and distributing those tasks (together with required data)
to the created `Agents`. `Manager` watch on the progress and stores the current results
to provide reports for `Addon` - so it is easy to restore progress if something goes
wrong.

`Addon` is watching on the status of `Manager` and provides to user the detailed report
and currently rendered image from the chosen task.

## API

* `Agent` providing a simple api to get status, upload the data and run the job.
* `Manager` have almost the same API as agent - to get current agents statuses in one
place and schedule jobs.

## TODOs

You can see all the feature requests/bugs on the github page:

* [Milestones](https://github.com/state-of-the-art/BlendNet/milestones)
* [Issues](https://github.com/state-of-the-art/BlendNet/issues)

### Tasks

* Use buckets to cache dependencies/results
* Cost estimation before rendering
* Denoising of the render result if option is enabled
* Distributed smoke baking (per-domain)
* Adding `AWS` and other cloud providers
* Allocating of preemptible GPU on the instances
* Detailed statistics to optimize the pipeline
* Simplify the setup process for the end-user
* Web interface to check the status

## Issues

If BlendNet saying "Something is wrong" or working incorrectly - it's the right place to find
the answer. BlendNet wants to automate the process as much as possible, but sometimes
environments are so much custom that the automation could work wrong. Let's check where you
can see the issues:

### Addon configuration

Addon is using provider's tools to for configuration. So check that your provider tool is available
in your PATH and working correctly: you should be able to create an instance and bucket in the
default project using the provider tool.

For example: To work with GCP and properly run the instances - you need a fresh `google cloud sdk`:
* Command `gcloud info` should print out where sdk is installed
* Command `gcloud auth list` should show the currently selected account
* Command `gcloud compute instances create test-instance` should actually create a new instance (you
can check that using google cloud web console at https://console.cloud.google.com/compute/instances)
* Command `gcloud compute instances delete test-instance` should actually delete the instance
* Command `gsutil mb gs://test-bucket-jsfkhbqfhbqw` should create a test bucket
* Command `gsutil rm -r gs://test-bucket-jsfkhbqfhbqw` should clean and delete the test bucket

Of course it's just an example  - but in general case those commands should work for you.

### Manager instance provisioning

This action actually using bucket creation, bucket files upload, instance creation, autostarting
script that downloads the Manager scripts from bucket and running them. After that Manager generates
CA and server SSL certificates and shares the CA certificate with the Addon. Addon tries to connect
the manager using ssl connection and the credentials from configuration (or generated ones).

What could go wrong here besides access to the GCP/Buckets from Addon:
* Error during start the Manager - check the serial console of the manager instance for logs of the
"startup-script".
* Instance service account access - BlendNet using default account with access scopes, so Manager
should already have the required rights to access buckets & GCE.
* Firewall rules - Addon should have access to the newly created/started Manager port (default 8443)
on the external IP. So make sure thet the rule was created by the Addon properly.

### Advanced users

Check the blender stdout - run it using console and you will see some debug messages from BlendNet.
If blender is started without console to check stdout - just restart it from console and try to
reproduce your steps to see additional information about the issue.

Also if you know how python is working - you can add more debug output to the BlendNet addon - just
edit the sources in it's directory, but please be carefull.

### Getting support

If you got no clues - you always can create an issue using this github repo, so we will try to help
and adjust the automation to make sure it will be fixed once and for all. But make sure you prepared
all the required information about the issue - you will need to describe your environment and
prepare steps to reproduce the issue you see.

## OpenSource

This is an experimental project - main goal is to test State Of The Art philosophy on practice.

We would like to see a number of independent developers working on the same project issues
for the real money (attached to the ticket) or just for fun. So let's see how this will work.

### License

Repository and it's content is covered by `Apache v2.0` - so anyone can use it without any concerns.

If you will have some time - it will be great to see your changes merged to the original repository -
but it's your choise, no pressure.

## Privacy policy

It's very important to save user private data and you can be sure: we working on security
of our applications and improving it every day. No data could be sent somewhere without
user notification and his direct approve. This application is using network connection
as minimum as possible to perform only the operations of it's main purpose. All the
connections are secured by the wide using open standards. Any internet connection will not
allow to collect any user personal data anyway.
