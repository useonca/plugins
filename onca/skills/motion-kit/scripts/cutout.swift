// Cut the subject of a photo out of its background with Apple's own Vision framework (macOS 14 or newer):
// nothing to download and nothing to license. usage: swift cutout.swift IN OUT.png
// Exit 2 bad arguments, 1 the photo could not be read or written, 3 no subject found.
import CoreImage
import Foundation
import ImageIO
import Vision

func fail(_ message: String, _ code: Int32 = 1) -> Never {
    FileHandle.standardError.write((message + "\n").data(using: .utf8)!)
    exit(code)
}

let args = CommandLine.arguments
if args.count != 3 { fail("usage: swift cutout.swift IN OUT.png", 2) }
let input = URL(fileURLWithPath: args[1])
let output = URL(fileURLWithPath: args[2])
guard let source = CGImageSourceCreateWithURL(input as CFURL, nil),
      let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else { fail("cannot read \(args[1])") }

let handler = VNImageRequestHandler(cgImage: image, options: [:])
let request = VNGenerateForegroundInstanceMaskRequest()
do { try handler.perform([request]) } catch { fail("Vision failed: \(error.localizedDescription)") }
guard let result = request.results?.first, !result.allInstances.isEmpty else { fail("no subject found in \(args[1])", 3) }

do {
    let masked = try result.generateMaskedImage(ofInstances: result.allInstances, from: handler, croppedToInstancesExtent: false)
    let picture = CIImage(cvPixelBuffer: masked)
    let space = CGColorSpace(name: CGColorSpace.sRGB)!
    try CIContext().writePNGRepresentation(of: picture, to: output, format: .RGBA8, colorSpace: space)
} catch {
    fail("cannot write \(args[2]): \(error.localizedDescription)")
}
