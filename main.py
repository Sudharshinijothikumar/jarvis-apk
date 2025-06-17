import kivy
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.clock import Clock, mainthread
from kivy.core.window import Window

import speech_recognition as sr
import pyttsx3
import json
import os
import difflib
import re
from datetime import datetime
import dateparser
import threading
from kivy.uix.image import Image
from kivy.uix.behaviors import ButtonBehavior

REMINDER_FILE = "reminders.json"
recognizer = sr.Recognizer()
voiceEngine = pyttsx3.init()
voiceEngine.setProperty('voice', voiceEngine.getProperty('voices')[0].id)

class JarvisLayout(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.padding = 10
        self.spacing = 10

        self.scroll = ScrollView(size_hint=(1, 0.85))
        self.log_label = Label(size_hint_y=None, text='', markup=True, valign='top', halign='left')
        self.log_label.bind(texture_size=self._update_height)
        self.scroll.add_widget(self.log_label)

        self.add_widget(self.scroll)

        class MicButton(ButtonBehavior, Image):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                self.source = "karaoke.png"
                self.size_hint = (1, 0.15)
                self.allow_stretch = True
                self.keep_ratio = True

        self.mic_button = MicButton()
        self.mic_button.bind(on_press=self.run_jarvis_thread)
        self.add_widget(self.mic_button)

        Clock.schedule_once(lambda dt: self.wish())

    def _update_height(self, instance, size):
        instance.height = instance.texture_size[1]
        instance.text_size = (self.scroll.width - 20, None)
        self.scroll.scroll_y = 0

    @mainthread
    def show_message(self, text, sender="user"):
        prefix = "[b][color=00ff00]Jarvis:[/color][/b] " if sender == "Jarvis" else "[b][color=ffffff]You:[/color][/b] "
        self.log_label.text += f"{prefix}{text}\n\n"

    def speak(self, text):
        self.show_message(text, sender="Jarvis")
        voiceEngine.say(text)
        voiceEngine.runAndWait()

    def listen(self, prompt=None, retries=3):
        if prompt:
            self.speak(prompt)
        for _ in range(retries):
            try:
                with sr.Microphone() as source:
                    self.show_message("Listening...", sender="Jarvis")
                    recognizer.adjust_for_ambient_noise(source, duration=1)
                    audio = recognizer.listen(source, timeout=10, phrase_time_limit=6)
                    command = recognizer.recognize_google(audio)
                    self.show_message(command, sender="user")
                    return command.lower()
            except sr.UnknownValueError:
                self.speak("Sorry, I didn't catch that.")
            except sr.RequestError:
                self.speak("Network issue.")
            except sr.WaitTimeoutError:
                self.speak("No response. Try again.")
        return ""

    def load_reminders(self):
        return json.load(open(REMINDER_FILE)) if os.path.exists(REMINDER_FILE) else {}

    def save_reminders(self, reminders):
        with open(REMINDER_FILE, "w") as f:
            json.dump(reminders, f, indent=4)

    def parse_datetime_input(self, text):
        time_pattern = r"\b\d{1,2}(:\d{2})?\s*(am|pm)?\b"
        date_keywords = [
            r"today", r"tomorrow", r"day after tomorrow", r"in \d+ (days?|weeks?|months?)",
            r"next (monday|tuesday|wednesday|thursday|friday|saturday|sunday|week|month)",
            r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}"
        ]
        date_pattern = "|".join(date_keywords)
        has_time = re.search(time_pattern, text)
        has_date = re.search(date_pattern, text, re.IGNORECASE)
        if has_date and has_time:
            return "both"
        elif has_date:
            return "date"
        elif has_time:
            return "time"
        else:
            return "none"

    def add_reminder(self):
        content = self.listen("What is the reminder about?")
        if not content:
            self.speak("Reminder content not received.")
            return
        reminder_info = {"content": content}

        if "doctor" in content:
            doctor_name = self.listen("What is the doctor's name?")
            reminder_info["doctor"] = doctor_name

        while True:
            datetime_input = self.listen("Tell me the date and time like 'tomorrow at 9 AM', or just say date or time.")
            if not datetime_input:
                continue
            date_time_type = self.parse_datetime_input(datetime_input)

            if date_time_type == "none":
                self.speak("I didn't catch a date or time. Please try again.")
                continue
            elif date_time_type == "date":
                self.speak("You gave only the date. Please say the time.")
                time_input = self.listen("Say the time like '9 AM' or '14:30'.")
                if not time_input:
                    continue
                datetime_input += " " + time_input
            elif date_time_type == "time":
                self.speak("You gave only the time. Please say the date.")
                date_input = self.listen("Say the date like 'tomorrow' or 'July 14'.")
                if not date_input:
                    continue
                datetime_input = date_input + " " + datetime_input

            date = dateparser.parse(datetime_input, settings={'PREFER_DATES_FROM': 'future'})
            if not date:
                self.speak("I couldn't understand that. Please try again.")
                continue
            if date < datetime.now():
                self.speak("That time has already passed. Please say a future time.")
                continue
            break

        reminder_info["datetime"] = date.strftime("%Y-%m-%d %H:%M")

        reminders = self.load_reminders()
        if reminder_info["datetime"] in reminders:
            self.speak(f"You already have a reminder at {reminder_info['datetime']}. Can't add another at the same time.")
            return

        for _ in range(3):
            repeat = self.listen("Repeat daily, weekly, monthly, yearly or one time?")
            if not repeat:
                continue
            repeat = repeat.lower().strip()
            if repeat in ["one time", "just once"]:
                repeat = "once"
            matched = difflib.get_close_matches(repeat, ["daily", "weekly", "monthly", "yearly", "once"], n=1, cutoff=0.6)
            if matched:
                reminder_info["repeat"] = matched[0]
                break
            else:
                self.speak("Please say daily, weekly, monthly, yearly, or once.")
        else:
            reminder_info["repeat"] = "once"

        self.speak(f"You said '{reminder_info['content']}' on {reminder_info['datetime']} repeating {reminder_info['repeat']}. Say 'do it' to confirm.")

        for _ in range(3):
            confirmation = self.listen()
            if "do it" in confirmation or "add it" in confirmation or "yes" in confirmation:
                reminders[reminder_info["datetime"]] = reminder_info
                self.save_reminders(reminders)
                self.speak("Reminder saved.")
                return
            elif "cancel" in confirmation or "no" in confirmation:
                self.speak("Reminder not saved.")
                return
            else:
                self.speak("Please say 'do it' to confirm or 'cancel' to stop.")
        self.speak("Reminder not saved after multiple attempts.")

    def view_reminders(self):
        reminders = self.load_reminders()
        if not reminders:
            self.speak("You have no reminders.")
            return
        now = datetime.now()
        upcoming = []
        for time_str, info in reminders.items():
            dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
            if dt >= now:
                upcoming.append((dt, info))
        if not upcoming:
            self.speak("No upcoming reminders.")
            return
        upcoming.sort()
        for time, info in upcoming:
            msg = f"{info['content']} on {time.strftime('%A, %B %d at %I:%M %p')}"
            if 'doctor' in info:
                msg += f", Doctor: {info['doctor']}"
            msg += f", Repeat: {info['repeat']}"
            self.speak(msg)

    def remove_reminder(self):
        target = self.listen("What reminder do you want to remove?")
        reminders = self.load_reminders()
        for k in list(reminders):
            if target in reminders[k]["content"].lower():
                self.speak(f"Found: {reminders[k]['content']} at {k}. Say 'do it' to confirm.")
                confirmation = self.listen()
                if "do it" in confirmation or "remove it" in confirmation or "yes" in confirmation:
                    del reminders[k]
                    self.save_reminders(reminders)
                    self.speak("Reminder removed.")
                    return
        self.speak("No matching reminder found.")

    def wish(self):
        hour = datetime.now().hour
        if hour < 12:
            self.speak("Good Morning!")
        elif hour < 18:
            self.speak("Good Afternoon!")
        else:
            self.speak("Good Evening!")
        self.speak("I am your assistant, Jarvis. How can I help you today?")

    def run_jarvis_thread(self, *args):
        threading.Thread(target=self.jarvis_main, daemon=True).start()

    def jarvis_main(self):
        command = self.listen("Your command?")
        if "add" in command:
            self.add_reminder()
        elif "view" in command or "show" in command:
            self.view_reminders()
        elif "remove" in command or "delete" in command:
            self.remove_reminder()
        elif "exit" in command or "stop" in command:
            self.speak("Goodbye!")
        else:
            self.speak("Unknown command. Try again.")

class JarvisApp(App):
    def build(self):
        Window.clearcolor = (0.1, 0.1, 0.1, 1)
        return JarvisLayout()

if __name__ == "__main__":
    JarvisApp().run()
