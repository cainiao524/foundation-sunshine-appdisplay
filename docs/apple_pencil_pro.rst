Apple Pencil Pro barrel roll
===========================

Windows hosts support the pen barrel-roll extension used by the supplied
``sunshine-1005.exe``. A compatible iPad client is required: a host upgrade alone
cannot make a client send Apple Pencil Pro rotation samples. Enable native
pen/touch input and mouse input in Sunshine, then reconnect the stream so the
client receives the updated capabilities.

Compatibility
-------------

The host advertises ``a=x-ss-general.penBarrelRoll:1`` in RTSP DESCRIBE when
Windows native pen input and mouse input are available. Compatible clients send
magic ``0x5500000B`` with the unchanged 36-byte ``SS_PEN_PACKET`` followed by a
little-endian 16-bit barrel-roll angle. The complete packet is 38 bytes, and its
big-endian size header is 34 (excluding the size field itself). Angles are in
degrees; ``0xFFFF`` means unknown.

The original ``rotation`` remains the tilt azimuth. The added barrel-roll angle
maps to Windows ``POINTER_PEN_INFO.rotation`` independently of tilt and pressure.
Legacy ``0x55000003`` packets retain their previous behavior. As in the reference
host, missing or unknown roll falls back to the legacy rotation; an explicit
zero angle is preserved. Other host platforms do not advertise barrel-roll
support.

Verification
------------

On an iPad with Apple Pencil Pro and a client supporting this extension:

* Connect to the Windows host with native pen input enabled.
* Open the existing native stylus input test tool or a drawing application that
  accepts Windows pen rotation.
* Hold tilt and pressure steady and twist the pencil. Rotation should change
  independently, including across 359/0 degrees.
* Tilt the pencil without twisting it and vary pressure. Tilt and pressure
  should continue to work independently.
* Check hover, pen down/up, side-button or eraser changes, and reconnecting.
* Reconnect an older client and verify its usual pen input still works.

The automated packet tests cover decoding, compatibility, angle normalization,
hover batching, contact samples, and truncated input. They do not replace this
device-and-application test.
