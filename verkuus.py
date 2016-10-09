
import sys, thread, time, Leap

from audiolazy import *
from numpy import *
from threading import Lock

# General timing variables
rate = 44100
s, Hz = sHz(rate)
ms = 1e-3 * s

## Any scales we want to use! All are in Hz, not MIDI or otherwise.
### B major = [B, C#, D#, E, F#, g#, A#]
bmajor_scale = [123.47, 138.6, 155.56, 164.8, 185, 207.65, 233.1, 246.94, 277.18, 311.13, 329.63, 370, 415.3, 466.16, 493.88, 554.37, 622.25, 659.26, 739.99]

### C major
cmajor_scale = [131, 147, 165, 175, 196, 220, 247]
cmajor_scale.extend(map(lambda x:x*2, cmajor_scale))
cmajor_scale.extend(map(lambda x:x*2, cmajor_scale))

### Pentatonic
pentatonic_scale = []
base_penta = 175
for j in range(0, 7):
    penta_dist = base_penta / 5
    for i in range(0, 5):
        pentatonic_scale.append(base_penta + penta_dist * i)
    base_penta *= 2

### Any of the chromatic notes
chromatic_scale = [175, 185, 196, 208, 220, 233, 247, 262, 277, 294, 311, 330, 349, 370, 391, 415, 440, 466, 494, 523, 554, 587, 622, 659, 698, 740, 784, 831]

### (float, int) -> float
### Gets some note x halfsteps from the given base note.
def get_note(base, halfsteps):
    return base * pow(1.059463, halfsteps)

### (float, [float]) -> float
### Returns note frequency corresponding to the given distance along the given scale.
def round_note(key_x, scale = bmajor_scale):
    print "rounding freq %s" % (key_x / 10)
    return scale[min(len(scale) - 1, max(0, int(abs(key_x / 10))))]

### Stream that can be changed after being used if the limit/append methods are
### called while playing. It uses an iterator that keep taking samples from the
### Stream instead of an iterator to the internal data itself.
class ChangeableStream(Stream):
  def __iter__(self):
    while True:
      yield next(self._data)

### Virtual keyboard that produces sounds from finger gestures.
class Keyboard(Leap.Listener):
    key_shift = 1 # Multiplier for the octave our keyboard starts at.
    mix = Streamix(True)
    streams = {}
    player = AudioIO(api=None)
    fingers_down = {} # Map of fingers down: {(is_left?, finger_idx): is_down?}
    mutex = Lock() # Use to sync our audio synthesis in case we run in multiple threads.
    attack = 100 * ms # How long a note fades in
    release = 450 * ms # How long a note plays after release
    level = .5  # Highest amplitude value per note

    ### Called when our sensor is ready.
    def on_init(self, controller):
        print "Initialized"
        self.player.play(self.mix, rate=rate)

    ### (Re)Connected to the sensor.
    def on_connect(self, controller):
        print "Connected"

    ### Disconnected from the sensor.
    def on_disconnect(self, controller):
        # NOTE: not dispatched when running in a debugger.
        print "Disconnected"

    def on_exit(self, controller):
        print "Exited"


    def play_sound(self, freq, synth):
        self.mutex.acquire()
        freq_str = str(freq) # Dict seems to need non-int keys to work right.
        freq *= self.key_shift
        if not freq_str in self.streams:
            ## Prepare the synth
            cs = ChangeableStream(self.level)
            env = line(self.attack, 0, self.level).append(cs)
            snd = env * synth(freq * Hz, tau=800*ms)
            ## Mix it, storing the stream to destroy later.
            self.streams[freq_str] = {'stream': cs, 'count': 1}
            self.mix.add(0, snd)
            print "playing freq %s" % (freq)
        else:
            entry = self.streams[freq_str]
            entry['count'] += 1
        self.mutex.release()

    def end_stream(self, s):
        s['stream'].limit(0).append(line(self.release, self.level, 0))

    def stop_sound(self, freq):
        self.mutex.acquire()
        freq_str = str(freq)
        if freq_str in self.streams:
            entry = self.streams[freq_str]
            ## Basic reference counting
            if entry['count'] > 1:
                entry['count'] -= 1
            else:
                ## We've lifted the last finger on this key, so stop the sound.
                self.end_stream(entry['stream'])
                del self.streams[freq_str]
        self.mutex.release()


    def on_frame(self, controller):
        used_freq = 0
        used_idx = 0
        ## Get the most recent frame and report some basic information
        frame = controller.frame()

        ## If we take away both hands, clear out all possibly pressed keys.
        if len(frame.hands) == 0:
            self.mutex.acquire()
            for k, s in self.streams.iteritems():
                self.end_stream(s['stream'])
            self.streams.clear()
            self.mutex.release()

        ## Check out one or both of our hands
        for hand in frame.hands:
            ## Skip this hand if the sensor isn't super confident about the fingers.
            if hand.confidence < 0.9:
                print "hand confidence = %f" % (hand.confidence)
                continue

            if hand.grab_strength > 0.95: # This hand is in a fist
                ## Look for twist gestures
                rot_dist = hand.rotation_angle(controller.frame(1), Leap.Vector.z_axis)
                if abs(rot_dist) > 0.06:
                    ## Shift our key by some amount based on the twisting.
                    ## To be detected, the twisting has to happen pretty quick.
                    self.key_shift += rot_dist / 3

            ## This hand has fingers.
            for finger in hand.fingers:
                if finger.type >= 0:
                    knuckle = finger.bone(2)
                    fingertip = finger.bone(3)
                    finger_diff_y = abs(hand.palm_position.y - fingertip.center.y)
                    finger_key = (hand.is_left, finger.type)
                    key_freq = knuckle.center.x
                    min_thumb_dist = 25
                    norm_diff = 0.2 # The threshold of curl for a finger to press a key.

                    ## This finger is lifting from a key.
                    if finger_key in self.fingers_down and ((finger.type is 0 and finger_diff_y > min_thumb_dist) or knuckle.direction.y <= norm_diff+0.03):
                        self.stop_sound(self.fingers_down[finger_key])
                        del self.fingers_down[finger_key]
                    ## The finger is starting to press a key.
                    elif ((finger.type is 0 and finger_diff_y <= min_thumb_dist) or knuckle.direction.y > norm_diff) and finger.tip_velocity.y < -300 and not finger_key in self.fingers_down:
                        ## If another finger played a note, play the right adjacent note.
                        if used_freq != 0:
                            key_freq = round_note(used_freq + 20 * (finger.type - used_idx))
                        else:
                            used_freq = key_freq

                        ## Left hand should play more of the bass end.
                        if hand.is_left:
                            key_freq -= 100
                        key_freq = round_note(key_freq)
                        self.play_sound(key_freq, karplus_strong)
                        self.fingers_down[finger_key] = key_freq


def main():
    # Create a keyboard and sensor controller
    listener = Keyboard()
    controller = Leap.Controller()

    ## Have the listener receive events from the controller
    listener.on_init(controller)
    while 1:
        listener.on_frame(controller)
        time.sleep(0.025) # Don't suck up CPU time.

    ## TODO: Exit with a key rather than Ctrl+C in console.
    ## This below runs multithreaded, so doesn't work as well with audio synthesis.
    ## controller.add_listener(listener)



if __name__ == "__main__":
    main()
