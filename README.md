# Verkuus

The virtual keytar to your heart.

## Inspiration
A friend told me about the Leap Motion sensors, and I had the idea to bring]
dreams of playing air instruments alive. Now, in a short timeframe the most
complicated and desirable result is quite difficult to implement: air guitar.
But so I started with a keyboard.

## What it does
 - Detects finger motion with the Leap Motion sensor and turns that into notes.
 - Can limit virtual notes to a specific key to make it easier to sound good :D
 - Tune the keyboard up or down by twisting your fist.
 - Play chords by using multiple fingers at once.

## How I built it
 - Used the Leap Motion API to start with, understanding how it tracks parts of the hands.
 - Converts the X-coordinate of a finger into a note by rounding to the nearest note in a key.
 - Check whether any of our fingers pressed down from our hand(s). If so, get a note for its position and play that note with a certain audio synthesis function.
 - The Leap Motion API has an endpoint in Python, so I started with that and experimenting with the sensor.

## Challenges I ran into
 - The Leap Motion api processes frames on multiple threads, so I had to sync up for audio synthesis since audio can only run on one thread.

## Accomplishments that I'm proud of
 - I kind of _finished_ something for a hackathon.
 - My first sensor project.

## What I learned
 - Clean, nice, tested code is hard to write in a short timeframe, especially working alone.

## What's next for Verkuus
 - Better code architecture.
 - Other instrument gestures: drums, guitar, etc.
 - More advanced audio synthesis and different synthesizers
 - Some kind of GUI to help users get a feel for the width and placement of virtual keys.
 - Different synthesizers for each hand.
