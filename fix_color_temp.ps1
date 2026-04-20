$f = 'C:\Users\a1318\WorkBuddy\xunfei_yuyin\iflyVoice\main.js'
$content = [System.IO.File]::ReadAllText($f, [System.Text.Encoding]::UTF8)
$old = @'
    async executeI2cCommand(controlName, value) {
        this.updateI2cStatus('executing');
        this.addDebugLog(`[Display] 设置 ${controlName} = ${value}`);

        if (this.displayType === 'native') {
            // 内置屏幕：WMI / DDC/CI
            await this._executeNativeCommand(controlName, value);
        } else {
            // ADB 显示器：DDC/CI over ADB
            await this._executeAdbCommand(controlName, value);
        }
    }

    async _executeNativeCommand(controlName, value) {
'@

$new = @'
    async executeI2cCommand(controlName, value) {
        this.updateI2cStatus('executing');
        this.addDebugLog('[Display] set ' + controlName + '=' + value);

        // colorTemp always uses gamma ramp (works on all displays, not DDC/CI)
        if (controlName === 'colorTemp') {
            await this._executeGammaCommand(controlName, value);
            return;
        }

        if (this.displayType === 'native') {
            await this._executeNativeCommand(controlName, value);
        } else {
            await this._executeAdbCommand(controlName, value);
        }
    }

    async _executeGammaCommand(controlName, value) {
        if (!this.nativeDisplay) {
            this.nativeDisplay = new window.NativeDisplayClient();
        }
        try {
            const result = await this.nativeDisplay.setColorTemp(value);
            if (result.success) {
                this.addDebugLog('[Gamma] ok colorTemp=' + value);
                this.updateI2cStatus('connected');
            } else {
                this.addDebugLog('[Gamma] fail: ' + result.error);
                this.appendI2cLog('error: ' + result.error, true);
                this.updateI2cStatus('error');
            }
        } catch (e) {
            this.addDebugLog('[Gamma] exception: ' + e.message);
            this.appendI2cLog('exception: ' + e.message, true);
            this.updateI2cStatus('error');
        }
    }

    async _executeNativeCommand(controlName, value) {
'@

if ($content.Contains($old)) {
    $content = $content.Replace($old, $new)
    [System.IO.File]::WriteAllText($f, $content, [System.Text.Encoding]::UTF8)
    Write-Host 'REPLACED'
} else {
    Write-Host 'NOT FOUND - trying line by line'
}
