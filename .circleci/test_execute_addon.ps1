# Runs the actual test on win platform

# Wait till the Manager service will be started
$counter = 0
do {
    if ( $counter -gt 30 ) {
        echo "Reached maximum retries ($i)"
        exit 1
    }
    $counter = $counter+1
    Write-Host "waiting ($counter)..."
    sleep 2
} until(Test-NetConnection "blendnet-manager-host" -Port 8443 | ? { $_.TcpTestSucceeded } )

$results_dir = 'results\addon'
mkdir -p $results_dir

$env:BLENDER_USER_SCRIPTS = "$pwd\scripts"
blender\blender.exe -b -noaudio test-project\proj\test-project.blend -P blendnet\.circleci\test_script_addon.py 2>&1 | tee -filepath "$results_dir\addon.log"

$remote_file = cat "$results_dir\addon.log" | Select-String -Pattern '^DATA: CI: ' | ForEach-Object { $_.ToString().split(' ', 3)[-1] }
if ($remote_file -eq $null) {
    echo "Not found the compose filepath in the test script output"
    exit 1
}

cp "$remote_file" "$results_dir"

echo "Check compose file size"
if ( (Get-Item $remote_file).length -lt 540*1024 ) {
    echo "File size is less then 540KB"
    exit 2
}

echo "Check exceptions in the log"
$result = cat "$results_dir\addon.log" | Select-String -Pattern '^Traceback'
if ($result -ne $null) {
    echo "Found exceptions in the addon log: $result"
    exit 3
}
echo "Check errors in the log"
$result = cat "$results_dir\addon.log" | Select-String -Pattern '^ERROR: '
if ($result -ne $null) {
    echo "Found errors in the addon log: $result"
    exit 4
}
$result = cat "$results_dir\addon.log" | Select-String -Pattern '^Fatal Python error: '
if ($result -ne $null) {
    echo "Found errors in the addon log: $result"
    exit 5
}

echo "Addon Compose image is received"
