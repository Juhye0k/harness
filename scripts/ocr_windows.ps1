param(
    [Parameter(Mandatory=$true)][string]$Manifest,
    [Parameter(Mandatory=$true)][string]$Output
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
Add-Type -AssemblyName System.Drawing
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime]
$null = [Windows.Storage.Streams.IRandomAccessStreamWithContentType, Windows.Storage.Streams, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrResult, Windows.Foundation, ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Globalization, ContentType=WindowsRuntime]
$asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
} | Select-Object -First 1
function Await-Result($Operation, [Type]$ResultType) {
    $task = $asTask.MakeGenericMethod($ResultType).Invoke($null, @($Operation))
    if (-not $task.Wait(15000)) { throw 'OCR operation timed out' }
    return $task.Result
}
Add-Type -ReferencedAssemblies System.Drawing -TypeDefinition @'
using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
public static class CaptionRegion {
    static bool Dark(Color c) { return c.R < 70 && c.G < 70 && c.B < 70; }
    static double Density(Bitmap b, int x, int y, int w) {
        int count = 0;
        for (int i = x; i < x + w; i++) if (Dark(b.GetPixel(i, y))) count++;
        return (double)count / w;
    }
    static bool InBox(Bitmap b, int x, int y, int w) {
        int margin = Math.Min(4, w);
        return Density(b, x, y, margin) + Density(b, x + w - margin, y, margin) > 1.0
            || Density(b, x, y, w) > .45;
    }
    public static int[] Extract(string input, string output) {
        using (var b = new Bitmap(input)) {
            int bestX = 0, bestY = 0, bestWidth = 0;
            for (int y = 0; y < b.Height; y++) {
                int start = 0;
                for (int x = 0; x <= b.Width; x++) {
                    if (x < b.Width && Dark(b.GetPixel(x, y))) continue;
                    int length = x - start;
                    if (length > bestWidth) { bestX = start; bestY = y; bestWidth = length; }
                    start = x + 1;
                }
            }
            if (bestWidth < 60) return null;
            int top = bestY, bottom = bestY;
            while (top > 0 && InBox(b, bestX, top - 1, bestWidth)) top--;
            while (bottom + 1 < b.Height && InBox(b, bestX, bottom + 1, bestWidth)) bottom++;
            if (bottom - top + 1 < 18) return null;
            var rect = new Rectangle(bestX, top, bestWidth, bottom - top + 1);
            using (var crop = b.Clone(rect, PixelFormat.Format32bppArgb))
            using (var scaled = new Bitmap(crop.Width * 2 + 40, crop.Height * 2 + 40)) {
                using (var graphics = Graphics.FromImage(scaled)) {
                    graphics.Clear(Color.White);
                    graphics.InterpolationMode = InterpolationMode.HighQualityBicubic;
                    using (var attr = new ImageAttributes()) {
                        attr.SetColorMatrix(new ColorMatrix(new float[][] {
                            new float[] {-1,0,0,0,0}, new float[] {0,-1,0,0,0},
                            new float[] {0,0,-1,0,0}, new float[] {0,0,0,1,0},
                            new float[] {1,1,1,0,1}}));
                        graphics.DrawImage(crop, new Rectangle(20,20,crop.Width*2,crop.Height*2),
                            0,0,crop.Width,crop.Height,GraphicsUnit.Pixel,attr);
                    }
                }
                scaled.Save(output, ImageFormat.Png);
            }
            return new int[] {bestX, top, bestWidth, bottom - top + 1};
        }
    }
}
'@
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new('ko'))
if ($null -eq $engine) { throw 'Installed Korean Windows OCR is required; no automatic download' }
if (Test-Path -LiteralPath $Output) { throw 'Output already exists; preserve previous runs' }
$manifestData = Get-Content -LiteralPath $Manifest -Raw -Encoding UTF8 | ConvertFrom-Json
$rows = @()
foreach ($frame in $manifestData.frames) {
    $cropPath = [IO.Path]::ChangeExtension($frame.path, ('.' + [IO.Path]::GetFileNameWithoutExtension($Output) + '.png'))
    if (Test-Path -LiteralPath $cropPath) { throw 'OCR crop already exists' }
    $region = [CaptionRegion]::Extract($frame.path, $cropPath)
    $text = ''
    if ($null -ne $region) {
        $file = Await-Result ([Windows.Storage.StorageFile]::GetFileFromPathAsync($cropPath)) ([Windows.Storage.StorageFile])
        $stream = Await-Result ($file.OpenReadAsync()) ([Windows.Storage.Streams.IRandomAccessStreamWithContentType])
        try {
            $decoder = Await-Result ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
            $bitmap = Await-Result ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
            try {
                $result = Await-Result ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
                $text = $result.Text
            } finally { $bitmap.Dispose() }
        } finally { $stream.Dispose() }
    }
    $rows += [ordered]@{time_ms=$frame.time_ms; text=$text; region=$region; frame_sha256=$frame.sha256; confidence=$null}
}
$report = [ordered]@{
    schema_version='source-caption-ocr-v1'; engine='windows-media-ocr'; language='ko';
    source_sha256=$manifestData.source_sha256; sample_step_ms=$manifestData.sample_step_ms;
    roi=$manifestData.roi; frames=$rows; external_calls=0; human_verified=$false
}
[IO.File]::WriteAllText([IO.Path]::GetFullPath($Output), ($report | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
Write-Output ('OCR frames processed: ' + $rows.Count)
