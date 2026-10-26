package io.mosip.registration.liveness;

/**
 * Common Face Capture Device Interface.
 *
 * Every supported L0/L1 device vendor implements this once, in its own
 * adapter module. The Liveness Orchestrator only ever talks to this
 * interface — it never depends on a specific vendor SDK.
 */
public interface FaceFrameSource {

    /** Begin streaming frames; onFrame is invoked for each captured frame. */
    void start(FrameListener listener) throws DeviceException;

    /** Stop streaming and release the device. */
    void stop();

    /** True if the device is currently connected and streaming. */
    boolean isConnected();

    /** Vendor/model identifier, for audit logging and diagnostics. */
    String getDeviceInfo();

    interface FrameListener {
        void onFrame(FaceFrame frame);
        void onDeviceError(DeviceException error);
        void onDisconnected();
    }

    class DeviceException extends Exception {
        public enum Reason {
            DEVICE_UNAVAILABLE,
            CONNECTION_FAILURE,
            CAMERA_UNAVAILABLE,
            UNSUPPORTED_FORMAT
        }

        private final Reason reason;

        public DeviceException(Reason reason, String message) {
            super(message);
            this.reason = reason;
        }

        public Reason getReason() { return reason; }
    }
}
