package io.mosip.registration.liveness;

import java.time.Instant;

/**
 * A single frame pulled from an L0/L1 biometric device.
 * Deliberately vendor-neutral: the Device Adapter layer is responsible
 * for converting whatever the vendor SDK hands back into this shape.
 */
public final class FaceFrame {

    private final byte[] imageData;   // raw pixel buffer, format per FrameFormat
    private final FrameFormat format;
    private final int width;
    private final int height;
    private final Instant capturedAt;

    public FaceFrame(byte[] imageData, FrameFormat format, int width, int height, Instant capturedAt) {
        this.imageData = imageData;
        this.format = format;
        this.width = width;
        this.height = height;
        this.capturedAt = capturedAt;
    }

    public byte[] getImageData() { return imageData; }
    public FrameFormat getFormat() { return format; }
    public int getWidth() { return width; }
    public int getHeight() { return height; }
    public Instant getCapturedAt() { return capturedAt; }

    public enum FrameFormat {
        RGB24,
        YUV420,
        JPEG
    }
}
