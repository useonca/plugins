// Cut a person out of their own talking clip with Apple's Vision framework (macOS 12 or newer): nothing to download
// and nothing to license. Writes one RGBA PNG per frame (OUTDIR/f000001.png ...) at the clip's size; kit.py presenter
// then encodes them as a transparent WebM.
// usage: swift presenter.swift IN.mp4 OUTDIR [--quality accurate|balanced]
// Exit 2 bad arguments, 1 the clip could not be read or a frame not written, 3 no person found in any frame.
import AVFoundation
import CoreImage
import Foundation
import Vision

func fail(_ message: String, _ code: Int32 = 1) -> Never {
    FileHandle.standardError.write((message + "\n").data(using: .utf8)!)
    exit(code)
}

var args = Array(CommandLine.arguments.dropFirst())
var quality = VNGeneratePersonSegmentationRequest.QualityLevel.balanced
if let k = args.firstIndex(of: "--quality") {
    guard k + 1 < args.count else { fail("--quality needs accurate or balanced", 2) }
    switch args[k + 1] {
    case "accurate": quality = .accurate
    case "balanced": quality = .balanced
    default: fail("--quality must be accurate or balanced, not \(args[k + 1])", 2)
    }
    args.removeSubrange(k...(k + 1))
}
if args.count != 2 { fail("usage: swift presenter.swift IN.mp4 OUTDIR [--quality accurate|balanced]", 2) }
let input = URL(fileURLWithPath: args[0])
let outDir = URL(fileURLWithPath: args[1], isDirectory: true)
do { try FileManager.default.createDirectory(at: outDir, withIntermediateDirectories: true) } catch {
    fail("cannot make \(args[1]): \(error.localizedDescription)")
}

let asset = AVURLAsset(url: input)
guard let track = asset.tracks(withMediaType: .video).first else { fail("no video in \(args[0])") }
let reader: AVAssetReader
do { reader = try AVAssetReader(asset: asset) } catch { fail("cannot read \(args[0]): \(error.localizedDescription)") }
let output = AVAssetReaderTrackOutput(track: track, outputSettings: [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA])
output.alwaysCopiesSampleData = false
reader.add(output)
if !reader.startReading() { fail("cannot read \(args[0]): \(reader.error?.localizedDescription ?? "unknown")") }

// Upright as played: the track's rotation (a phone clip shot portrait) as an orientation. CIImage counts y up,
// so the transform itself cannot be applied as is; its angle picks the orientation.
func orientation(_ t: CGAffineTransform) -> CGImagePropertyOrientation {
    switch Int((atan2(Double(t.b), Double(t.a)) * 180 / Double.pi).rounded()) {
    case 90: return .right
    case -90, 270: return .left
    case 180, -180: return .down
    default: return .up
    }
}
func upright(_ image: CIImage, _ o: CGImagePropertyOrientation) -> CIImage {
    let turned = image.oriented(o)
    return turned.transformed(by: CGAffineTransform(translationX: -turned.extent.minX, y: -turned.extent.minY))
}
let turn = orientation(track.preferredTransform)

let request = VNGeneratePersonSegmentationRequest()
request.qualityLevel = quality
request.outputPixelFormat = kCVPixelFormatType_OneComponent8
let sequence = VNSequenceRequestHandler()
let context = CIContext()
let space = CGColorSpace(name: CGColorSpace.sRGB)!
let clear = CIImage(color: .clear)
var index = 0
var found = false

while let sample = output.copyNextSampleBuffer() {
    guard let pixels = CMSampleBufferGetImageBuffer(sample) else { continue }
    index += 1
    let frame = CIImage(cvPixelBuffer: pixels)
    let picture = upright(frame, turn)
    var cut = picture
    do {
        try sequence.perform([request], on: pixels, orientation: .up)
        if let maskBuffer = request.results?.first?.pixelBuffer {
            var mask = CIImage(cvPixelBuffer: maskBuffer)
            mask = mask.transformed(by: CGAffineTransform(scaleX: frame.extent.width / mask.extent.width,
                                                          y: frame.extent.height / mask.extent.height))
            mask = upright(mask, turn)
            mask = mask.clampedToExtent().applyingGaussianBlur(sigma: 1.5).cropped(to: picture.extent)
            let average = mask.applyingFilter("CIAreaAverage", parameters: [kCIInputExtentKey: CIVector(cgRect: mask.extent)])
            var px = [UInt8](repeating: 0, count: 4)
            context.render(average, toBitmap: &px, rowBytes: 4, bounds: CGRect(x: 0, y: 0, width: 1, height: 1),
                           format: .RGBA8, colorSpace: nil)
            if px[0] > 2 { found = true }
            cut = picture.applyingFilter("CIBlendWithMask", parameters: [kCIInputBackgroundImageKey: clear.cropped(to: picture.extent),
                                                                        kCIInputMaskImageKey: mask])
        }
    } catch {
        fail("Vision failed on frame \(index): \(error.localizedDescription)")
    }
    let file = outDir.appendingPathComponent(String(format: "f%06d.png", index))
    do { try context.writePNGRepresentation(of: cut, to: file, format: .RGBA8, colorSpace: space) } catch {
        fail("cannot write \(file.path): \(error.localizedDescription)")
    }
}
if reader.status == .failed { fail("cannot read \(args[0]): \(reader.error?.localizedDescription ?? "unknown")") }
if index == 0 { fail("no frames in \(args[0])") }
if !found { fail("no person found in \(args[0])", 3) }
print("\(index) frames -> \(outDir.path)")
