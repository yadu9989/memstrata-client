[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$OutputDirectory
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing

$resolvedOutput = [System.IO.Path]::GetFullPath($OutputDirectory)
[System.IO.Directory]::CreateDirectory($resolvedOutput) | Out-Null

function Write-PlaceholderPng {
    param(
        [string]$Name,
        [int]$Width,
        [int]$Height
    )

    $bitmap = [System.Drawing.Bitmap]::new($Width, $Height)
    try {
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
        try {
            $graphics.Clear([System.Drawing.Color]::FromArgb(8, 24, 47))
            $brush = [System.Drawing.SolidBrush]::new(
                [System.Drawing.Color]::FromArgb(62, 207, 255)
            )
            try {
                $fontSize = [Math]::Max(10, [Math]::Min($Width, $Height) * 0.48)
                $font = [System.Drawing.Font]::new(
                    "Segoe UI",
                    $fontSize,
                    [System.Drawing.FontStyle]::Bold,
                    [System.Drawing.GraphicsUnit]::Pixel
                )
                try {
                    $format = [System.Drawing.StringFormat]::new()
                    try {
                        $format.Alignment = [System.Drawing.StringAlignment]::Center
                        $format.LineAlignment = [System.Drawing.StringAlignment]::Center
                        $rect = [System.Drawing.RectangleF]::new(0, 0, $Width, $Height)
                        $graphics.DrawString("M", $font, $brush, $rect, $format)
                    }
                    finally {
                        $format.Dispose()
                    }
                }
                finally {
                    $font.Dispose()
                }
            }
            finally {
                $brush.Dispose()
            }
        }
        finally {
            $graphics.Dispose()
        }
        $path = Join-Path $resolvedOutput $Name
        $bitmap.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
    }
    finally {
        $bitmap.Dispose()
    }
}

Write-PlaceholderPng "StoreLogo.png" 50 50
Write-PlaceholderPng "Square44x44Logo.png" 44 44
Write-PlaceholderPng "Square71x71Logo.png" 71 71
Write-PlaceholderPng "Square150x150Logo.png" 150 150
Write-PlaceholderPng "Wide310x150Logo.png" 310 150
Write-PlaceholderPng "Square310x310Logo.png" 310 310

Write-Warning "Generated PLACEHOLDER artwork. Replace it with approved Store assets before submission."
