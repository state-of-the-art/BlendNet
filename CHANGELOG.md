## [v0.3.0](https://github.com/state-of-the-art/BlendNet/issues?q=milestone%3Av0.3.0)

### Providers:
 - AWS cloud provider
 - Cloud providers price get per instance type
 - Receive cloud instance logs
 - Local provider

### Addon:
 - Moved provider manager/agent type to addon preferences
 - Render memory constraint to the scene settings
 - Show calculated cloud prices
 - When Manager is active - switches to it's API to get resources
 - Show the instance/service logs in separated window
 - Show task additional info in a better way
 - Checks available Blender version from newest to oldest
 - Automatically download compositing instead of huge render result
 - Task actions to manually download render and compose results
 - Task preview now uses temp directory and downloads previews in background
 - List of the Agents
 - Button to remove any Agent
 - UI shows status of the Agent

### Manager:
 - Compositing support (for now executed on Manager, but will be moved to the Agent #65)
 - Saving to the user defined format and file output
 - Provide logs from the running service
 - Rewrote the task processes for better stability
 - Exposed API to show the controlled resources

### Agent:
 - Provide logs from the running service

### Bugfixes:
 - Addon: download only the related to the opened project task results
 - Manager: fixed a couple of deadlocks and stopping process to not recreate the destroyed Agents
 - Manager: improved error task state handling
 - Agent: render results was one-layer exr, instead of multilayer ones

### Additional:
 - Prepared CI to test the Addon and API on test-project (useful as automation examples)
 - Improved Wiki with automation articles and more info about BlendNet
 - New test project release v0.3 with compose support
 - More debugging info
