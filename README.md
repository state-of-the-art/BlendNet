BlendNet
========

[![Join the chat at https://gitter.im/state-of-the-art/BlendNet](https://badges.gitter.im/state-of-the-art/BlendNet.svg)](https://gitter.im/state-of-the-art/BlendNet?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge)
[![CircleCI master build](https://circleci.com/gh/state-of-the-art/BlendNet/tree/master.svg?style=shield)](https://app.circleci.com/pipelines/github/state-of-the-art/BlendNet?branch=master)

[![CircleCI nightly 2.80](https://img.shields.io/badge/dynamic/json?label=nightly%202.80&query=%24%5B%3F%28%40.branch%20%3D%3D%20%22master%22%20%26%26%20%40.workflows.workflow_name%20%3D%3D%20%22nightly_test%22%20%26%26%20%40.workflows.%20job_name%20%3D%3D%20%22blendnet_test-1%22%29%5D.status&url=https%3A%2F%2Fcircleci.com%2Fapi%2Fv1.1%2Fproject%2Fgh%2Fstate-of-the-art%2FBlendNet%3Flimit%3D15)](https://app.circleci.com/pipelines/github/state-of-the-art/BlendNet?branch=master) - testing BlendNet with Blender 2.80 every night

[![CircleCI nightly LTS](https://img.shields.io/badge/dynamic/json?label=nightly%20lts&query=%24%5B%3F%28%40.branch%20%3D%3D%20%22master%22%20%26%26%20%40.workflows.workflow_name%20%3D%3D%20%22nightly_test%22%20%26%26%20%40.workflows.%20job_name%20%3D%3D%20%22blendnet_test-2%22%29%5D.status&url=https%3A%2F%2Fcircleci.com%2Fapi%2Fv1.1%2Fproject%2Fgh%2Fstate-of-the-art%2FBlendNet%3Flimit%3D15)](https://app.circleci.com/pipelines/github/state-of-the-art/BlendNet?branch=master) - testing BlendNet with Blender LTS every night

[![CircleCI nightly Latest](https://img.shields.io/badge/dynamic/json?label=nightly%20latest&query=%24%5B%3F%28%40.branch%20%3D%3D%20%22master%22%20%26%26%20%40.workflows.workflow_name%20%3D%3D%20%22nightly_test%22%20%26%26%20%40.workflows.%20job_name%20%3D%3D%20%22blendnet_test-3%22%29%5D.status&url=https%3A%2F%2Fcircleci.com%2Fapi%2Fv1.1%2Fproject%2Fgh%2Fstate-of-the-art%2FBlendNet%3Flimit%3D15)](https://app.circleci.com/pipelines/github/state-of-the-art/BlendNet?branch=master) - testing BlendNet with Blender latest release every night

Blender network rendering farm system with dynamic allocating of required resources.

* [Site page about it](https://www.state-of-the-art.io/projects/blendnet/)

## Usage

Please check out the wiki page: [Wiki](https://github.com/state-of-the-art/BlendNet/wiki) - it
contains more information about how to setup each supported provider and some useful details.

## Requirements

* Blender >= 2.80 (2.81, 2.82, 2.83.1, 2.9, ...) - as a host for the Addon
* If you have a plan to use a cloud provider:
    * Google Cloud Platform (GCP)
        * Installed `Google Cloud SDK`
        * gcloud credentials (user or service account)
        * Existing project with activated compute api
        * Quotas ready to run planned amount of resources
    * Amazon Web Services
        * Installed `AWS CLI V2`
        * Configured aws tool access key

## Purpose

Existing Blender addons that enable network rendering on a cluster of instances
are too complicated, not enough automated or too expensive. The solution is just
to use the existing cloud providers with their cheap preemptible instances that
costs ~3 times less than the regular ones.

For example `GCP` n1-highcpu-64 (**64 core 57.6GB RAM**) will cost you just
**$0.48 per hour**. Just imagine this - a quite complicated `Cycles engine` frame
will cost just $0.50 and with using and with using optimization techniques less
than $0.10.

## Challenges

But yeah, it's not easy - preemptible instances are quite unstable and usually could
be terminated without any notification by the GCP engine in any minute. So we need a
system that will allow us to make sure that:

1. We can easily run a number new instances by clicking just one button in Blender
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

It's integrated with the current Blender render engine and allows user to send the
same configuration to the Manager to use the cloud resources for rendering.

Area of responsibility:
* User UI with a way to configure and monitor the BlendNet activity.
* Create the Manager instance and watch its status.
* Specifies tasks (one per frame) and upload the required dependencies for them.
* Restore connection on restart - so it's possible to retrieve the results.
* Shows the rendering process with detailed status and previews.

It's also making sure that the project contains all the required dependencies, like
textures, caches, physic bakes and so on - Agents will render just one frame, so it
should already contain all the required caches before starting to render.

### Manager

Required to make sure - even if Blender will be closed, the rendering process will
be continued and the results will not be lost. Will execute the tasks sequentially -
if the current task is almost complete and has waiting resources, it will start the
next one to load the resources as much as possible.

Area of responsibility:
* Allocating resources according to the task specification.
* Manages the allocated resources (if some resources going offline - restores it).
* Planning the load (resources should work, not wait for dependencies).
* Collects and merges the previews and results from the Agents.
* Saving your money as much as possible.

When a task is marked to execute - Manager starts it and prepars a plan: it needs
to create the Agents, determine the number of samples per Agent, upload the
dependencies to them, run the execution and watch for the status and progress.
Meanwhile, it should plan for the next task (if there are some) - preload the
dependencies and put it on hold.

It will leave the Agents active for a short period of time after the rendering process
(by default 5 mins), will stop them after that. It will delete Agents and stop itself
if there are no tasks for 30 mins (by default).

Tasks are coming from Addon: one task - one frame. Tasks have a number of samples to
render - and the Manager decides how many samples it will give to an Agent. The Manager
tries to keep the ratio loading/rendering relatively lower, but less than 30 mins per
Agent task. By default it's 100 samples per Agent task.

#### Security

The Manager can control instances (Agents) in the project, can write/read to/from the
project buckets and have an external IP. All the connections are encrypted and access
is protected by a strong generated password, but it's a good idea to stop the instance
when it's not needed anymore (by default timeout is set to 30 mins).

### Agent

Main workhorse of the system - receiving tasks, dependencies, configs and starting
working on it. Reports status and previews back - so Manager (and user) could watch on
progress.

Area of responsibility:
* Receives granular tasks from the Manager with all the dependencies.
* Executes the rendering process with verbose reports of the status.
* Captures periodic previews to show the preliminary results.
* Captures render result.
* Watching on self-health status - if going to shutdown, captures the render result.

#### Security

The Agent has an external IP for a short period of time to get the required Blender
dependencies - after that it's removed by the Manager. All the connections are
encrypted and access is protected by a strong generated password.

## Protection

Since we don't want anyone but us to see our information or use our resources -
BlendNet provides 2 simple protection mechanisms: BasicAuth and TLS.

### Basic Auth

Is a simple HTTP mechanism to make sure the only one who has the right credentials can
access the server resources. During Manager setup Addon generates (or uses a preset)
pair of user/password - they are stored as Manager configuration.

When Addon wants to talk with Manager - it provides credentials in the HTTP request
header, Manager compares those creds with the stored ones and if they are ok - allow
the request and respond.

Almost the same process happening between Manager and Agent - but with Agent
credentials.

Those credentials are passed to the Manager/Agent as clear text, so BlendNet uses TLS
to encrypt the whole communication between client and server.

### TLS

Required to encrypt the message transport - so no one but client and server can read
those messages during transmission. That means any communication or transfer between
Addon & Manager or Manager and Agent is completely encrypted.

TLS uses asymmetric encryption that involves 2 keys - private and public. In case of
TLS public key file also contains some readable information and called certificate.

When Manager is created the first time - it generates a custom Certificate Authority
certificate and signs all the generated certificates with this CA certificate.
Manager uploads this certificate back to the bucket and Addon can use it to confirm
that this Manager is the one Addon needs.

When the Manager creates Agents - it generates certificates for each one and uses CA to
confirm the identity of the Agents.

## Pipeline

Blender `Addon` gets the required credentials to run instances on providers (`GCP`,
`AWS`, ...) or uses the `local` one. User also configures some settings for the
providers - what kind of instances he would like to use, timeouts and cost limits.
Also, it checks for the proper setup of the project - make sure quotas and permissions
are setup correctly.

When a user chooses to start a task - addon saving a temporary blend file and creating
the `Manager` (locally or on the provider instance - depends on user choice). It's
passing the blend file, resources, local baked caches and a task specification to work
on.

`Manager` allocates the required resources and starts the `Agent` workers. Splitting the
task into a number of tasks and distributing those tasks (together with required data)
to the created `Agents`. `Manager` watches the progress and stores the current results
to provide reports for `Addon` - so it is easy to restore progress if something goes
wrong.

`Addon` is watching the status of the `Manager` and provides the user with a detailed
report and currently rendered image from the chosen task.

## API

* `Agent` provides a simple API to get status, upload the data and run the job.
* `Manager` have almost the same API as Agent - to get current Agents statuses in one
place and schedule jobs.

## TODOs

You can see all the feature requests/bugs on the github page:

* [Milestones](https://github.com/state-of-the-art/BlendNet/milestones)
* [Issues](https://github.com/state-of-the-art/BlendNet/issues)

### Tasks

* Use buckets to cache dependencies/results
* Cost estimation before rendering
* Distributed smoke baking (per-domain): it's hard to bake multiple domains - it requires one domain
  per bake, others should be turned off
* Allocating of preemptible GPU on the instances
* Detailed statistics to optimize the pipeline
* Web interface to check the status

### Advanced users

Check the Blender stdout - run it using console and you will see some debug messages from BlendNet.
If Blender is started without a console to check stdout - just restart it from console and try to
reproduce your steps to see additional information about the issue.

Also if you know how python is working - you can add more debug output to the BlendNet addon - just
edit the sources in it's directory, but please be careful.

### Getting support

If you got no clues - you always can create an issue using this github repo, so we will try to help
and adjust the automation to make sure it will be fixed once and for all. But make sure you prepared
all the required information about the issue - you will need to describe your environment and
prepare steps to reproduce the issue you see.

## OpenSource

This is an experimental project - main goal is to test State Of The Art philosophy in practice.

We would like to see a number of independent developers working on the same project issues
for the real money (attached to the ticket) or just for fun. So let's see how this will work.

### License

Repository and it's content is covered by `Apache v2.0` - so anyone can use it without any concerns.

If you will have some time - it will be great to see your changes merged to the original repository -
but it's your choice, no pressure.

## Privacy policy

It's very important to save user private data and you can be sure: we are working on security
of our applications and improving it every day. No data could be sent somewhere without
user notification and his direct approval. This application is using network connection
as minimum as possible to perform only the operations of it's main purpose. All the
connections are secured by the wide using open standards. Any internet connection will not
allow to collect any user personal data anyway.
