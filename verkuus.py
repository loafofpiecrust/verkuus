
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

### Virtual keyboard that produces sounds from
class Keyboard(Leap.Listener):
    finger_names = ['Thumb', 'Index', 'Middle', 'Ring', 'Pinky']
    bone_names = ['Metacarpal', 'Proximal', 'Intermediate', 'Distal']

    curr_y = 0
    key_shift = 1
    mix = Streamix(True)
    streams = {}
    player = AudioIO(api=None)
    fingers_down = {}
    mutex = Lock()
    attack = 100 * ms # How long a note fades in
    release = 450 * ms # How long a note plays after release
    level = .5  # Highest amplitude value per note

    def on_init(self, controller):
        print "Initialized"
        self.player.play(self.mix, rate=rate)

    def on_connect(self, controller):
        print "Connected"
        #controller.enable_gesture(Leap.Gesture.TYPE_KEY_TAP)
        controller.enable_gesture(Leap.Gesture.TYPE_CIRCLE)

    def on_disconnect(self, controller):
        # Note: not dispatched when running in a debugger.
        print "Disconnected"

    def on_exit(self, controller):
        print "Exited"

    def pluck_string(self, freq, synth, speed):
        self.mutex.acquire()
        #freq = round_note(freq)
        level = 0.5
        freq_str = str(freq)
        freq = self.key_shift * freq
        if not freq_str in self.streams:
            # Prepares the synth
            #freq = notes[ch]
            cs = ChangeableStream(self.level)
            env = line(self.attack, 0, self.level).append(cs)
            snd = env * synth(freq * Hz, tau=800*ms)
            # Mix it, storing the ChangeableStream to be changed afterwards
            self.streams[freq_str] = {'stream': cs, 'count': 1}
            print "playing freq %s" % (freq)
            self.mix.add(0, snd)
        else:
            entry = self.streams[freq_str]
            entry['count'] += 1
        self.mutex.release()


    def stop_sound(self, freq):
        self.mutex.acquire()
        #ch = evt.char
        #freq = round_note(freq)
        freq_str = str(freq)
        if freq_str in self.streams:
            entry = self.streams[freq_str]
            if entry['count'] > 1:
                entry['count'] -= 1
            else:
                entry['stream'].limit(0).append(line(self.release, self.level, 0))
                del self.streams[freq_str]
        self.mutex.release()


    def on_frame(self, controller):
        used_freq = 0
        used_idx = 0
        # Get the most recent frame and report some basic information
        frame = controller.frame()


        if len(frame.hands) == 0:
            self.mutex.acquire()
            for k, s in self.streams.iteritems():
                s['stream'].limit(0).append(line(self.release, self.level, 0))
            self.streams.clear()
            self.mutex.release()
        for hand in frame.hands:
            if hand.confidence < 0.9:
                print "hand confidence = %f" % (hand.confidence)
                continue

            if hand.grab_strength > 0.95:
                # look for twist gestures
                # this signals us to look for twisting
                rot_dist = hand.rotation_angle(controller.frame(1), Leap.Vector.z_axis)
                if abs(rot_dist) > 0.06:
                    print "fist rotation: %s" % (rot_dist)
                    self.key_shift += rot_dist / 3

            for finger in hand.fingers:
                if finger.type >= 0:
                    knuckle = finger.bone(2)
                    fingertip = finger.bone(3)
                    key_y = 20
                    key_height = 15
                    tip_pos = fingertip.center
                    hand_pos = hand.palm_position
                    finger_diff_y = abs(hand_pos.y - tip_pos.y)
                    finger_key = (hand.is_left, finger.type)
                    hand_x = hand.palm_position.x
                    key_freq = knuckle.center.x
                    min_dist = 30
                    min_angle = 5.0
                    norm_diff = 0.2

                    if finger_key in self.fingers_down and ((finger.type is 0 and finger_diff_y > min_dist) or knuckle.direction.y <= norm_diff+0.03):
                        self.stop_sound(self.fingers_down[finger_key])
                        del self.fingers_down[finger_key]
                    elif ((finger.type is 0 and finger_diff_y <= min_dist) or knuckle.direction.y > norm_diff) and finger.tip_velocity.y < -300 and not finger_key in self.fingers_down:
                        ## If another finger played a note, play the right adjacent note.
                        if used_freq != 0:
                            key_freq = round_note(used_freq + 20 * (finger.type - used_idx))
                        else:
                            used_freq = key_freq

                        fingertip = finger.bone(3)
                        tip_dir = fingertip.direction
                        self.curr_y = tip_dir.y
                        if hand.is_left:
                            key_freq -= 100
                        key_freq = round_note(key_freq)
                        self.pluck_string(key_freq, karplus_strong, finger.tip_velocity.magnitude)
                        self.fingers_down[finger_key] = key_freq


def main():

    # Create a sample listener and controller
    listener = Keyboard()
    controller = Leap.Controller()

    # Have the sample listener receive events from the controller
    #controller.add_listener(listener)
    listener.on_init(controller)
    while 1:
        listener.on_frame(controller)
        time.sleep(0.025)

    # TODO: Exit with a key rather than Ctrl+C in console.



if __name__ == "__main__":
    main()
