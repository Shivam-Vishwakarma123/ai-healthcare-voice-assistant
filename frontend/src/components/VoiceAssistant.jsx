import { useEffect, useRef, useState } from "react";
import { apiRequest } from "../services/api";
import { useToast } from "./ToastProvider";

export default function VoiceAssistant({ token, language = "en" }) {
  const toast = useToast();
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const [transcriptionBusy, setTranscriptionBusy] = useState(false);
  const [speechConfig, setSpeechConfig] = useState(null);
  const [speechConfigError, setSpeechConfigError] = useState("");
  const [transcriptNeedsConfirmation, setTranscriptNeedsConfirmation] = useState(false);
  const [error, setError] = useState("");
  const recognitionRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const mediaStreamRef = useRef(null);
  const recordedChunksRef = useRef([]);
  const recordingTimeoutRef = useRef(null);
  const hi = language === "hi";
  useEffect(() => {
    if (!error) return;
    toast(error, "error");
    setError("");
  }, [error, toast]);
  useEffect(() => {
    let active = true;
    apiRequest("/assistant/speech-to-text/config", token)
      .then((config) => {
        if (active) setSpeechConfig(config);
      })
      .catch((reason) => {
        if (active) setSpeechConfigError(reason.message || "Speech input settings could not be loaded.");
      });
    return () => {
      active = false;
      recognitionRef.current?.stop();
      if (mediaRecorderRef.current?.state === "recording") {
        mediaRecorderRef.current.onstop = null;
        mediaRecorderRef.current.stop();
      }
      mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
      window.clearTimeout(recordingTimeoutRef.current);
    };
  }, [token]);

  async function sendMessage(event) {
    event?.preventDefault();
    const content = draft.trim();
    if (!content || busy || transcriptionBusy || transcriptNeedsConfirmation) return;
    const nextMessages = [...messages, { role: "user", content }];
    setMessages(nextMessages);
    setDraft("");
    setError("");
    setBusy(true);
    try {
      const result = await apiRequest("/assistant/chat", token, {
        method: "POST",
        body: JSON.stringify({ messages: nextMessages.slice(-20) }),
      });
      const answer = { role: "assistant", content: result.reply, citations: result.citations || [] };
      setMessages((current) => [...current, answer]);
    } catch (requestError) {
      setError(requestError.message);
      setMessages((current) => current.slice(0, -1));
      setDraft(content);
    } finally {
      setBusy(false);
    }
  }

  function startListening() {
    setError("");
    if (!speechConfig) {
      setError(speechConfigError || (hi ? "वॉइस सेटिंग लोड हो रही हैं। कृपया प्रतीक्षा करें या लिखें।" : "Voice settings are loading. Please wait or type your message."));
      return;
    }
    if (speechConfig.provider !== "browser") {
      void startServerRecording();
      return;
    }
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setError("Voice input is not supported in this browser. Try a current version of Chrome or Edge, or type your message.");
      return;
    }
    const recognition = new SpeechRecognition();
    recognition.lang = hi ? "hi-IN" : "en-IN";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.onresult = (event) => {
      setDraft(event.results[0][0].transcript);
      setTranscriptNeedsConfirmation(true);
    };
    recognition.onerror = (event) => setError(`Microphone could not transcribe speech (${event.error}). Check browser microphone permission.`);
    recognition.onend = () => setListening(false);
    recognitionRef.current = recognition;
    setListening(true);
    try {
      recognition.start();
    } catch {
      setListening(false);
      setError("Could not start voice capture. Check microphone permission and try again.");
    }
  }

  async function startServerRecording() {
    if (!speechConfig?.transcription_enabled) {
      setError(hi ? "कॉन्फ़िगर किया गया वॉइस प्रदाता उपलब्ध नहीं है। आप लिखकर जारी रख सकते हैं।" : "The configured speech provider is unavailable. You can continue by typing.");
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setError(hi ? "यह ब्राउज़र रिकॉर्डिंग का समर्थन नहीं करता। कृपया लिखें।" : "This browser cannot record audio. Please type your message.");
      return;
    }
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = ["audio/webm;codecs=opus", "audio/ogg;codecs=opus", "audio/mp4"]
        .find((type) => window.MediaRecorder.isTypeSupported(type));
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      mediaStreamRef.current = stream;
      mediaRecorderRef.current = recorder;
      recordedChunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) recordedChunksRef.current.push(event.data);
      };
      recorder.onerror = () => {
        setError(hi ? "ऑडियो रिकॉर्डिंग विफल हुई। कृपया दोबारा प्रयास करें या लिखें।" : "Audio recording failed. Try again or type your message.");
        recorder.onstop = null;
        if (recorder.state === "recording") recorder.stop();
        stopMediaStream();
        setListening(false);
      };
      recorder.onstop = () => {
        window.clearTimeout(recordingTimeoutRef.current);
        stopMediaStream();
        setListening(false);
        void transcribeRecording(recorder.mimeType || "audio/webm");
      };
      recorder.start();
      setListening(true);
      recordingTimeoutRef.current = window.setTimeout(() => {
        if (recorder.state === "recording") recorder.stop();
      }, 60_000);
    } catch {
      stream?.getTracks().forEach((track) => track.stop());
      setListening(false);
      setError(hi ? "माइक्रोफ़ोन शुरू नहीं हो सका। अनुमति जाँचें या लिखें।" : "Could not start the microphone. Check permission or type your message.");
    }
  }

  function stopMediaStream() {
    mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    mediaStreamRef.current = null;
  }

  async function transcribeRecording(mimeType) {
    const audio = new Blob(recordedChunksRef.current, { type: mimeType });
    recordedChunksRef.current = [];
    if (!audio.size) {
      setError(hi ? "कोई ऑडियो रिकॉर्ड नहीं हुआ। कृपया फिर से बोलें या लिखें।" : "No audio was recorded. Try again or type your message.");
      return;
    }
    if (audio.size > speechConfig.max_audio_bytes) {
      setError(hi ? "रिकॉर्डिंग आकार सीमा से बड़ी है। छोटा संदेश रिकॉर्ड करें या लिखें।" : "The recording exceeds the size limit. Record a shorter message or type it.");
      return;
    }
    setTranscriptionBusy(true);
    setError("");
    try {
      const extension = mimeType.includes("ogg") ? "ogg" : mimeType.includes("mp4") ? "mp4" : "webm";
      const form = new FormData();
      form.append("file", audio, `voice.${extension}`);
      form.append("language", hi ? "hi" : "en");
      const result = await apiRequest("/assistant/speech-to-text", token, {
        method: "POST",
        body: form,
      });
      setDraft(result.transcript);
      setTranscriptNeedsConfirmation(result.requires_confirmation);
    } catch (reason) {
      setError(reason.message || (hi ? "आवाज़ लिखित रूप में नहीं बदली जा सकी। आप लिखकर जारी रख सकते हैं।" : "Audio could not be transcribed. You can continue by typing."));
    } finally {
      setTranscriptionBusy(false);
    }
  }

  function speak(content) {
    if (!("speechSynthesis" in window)) {
      setError("Speech playback is not supported in this browser.");
      return;
    }
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(new SpeechSynthesisUtterance(content));
  }

  return (
    <section className="voice-layout">
      <div className="card voice-card">
        <div className="voice-orb" aria-hidden="true">◉</div>
        <span className="eyebrow">{hi ? "वॉइस सहायक" : "VOICE ASSISTANT"}</span>
        <h2>{hi ? "आपको किस बारे में मदद चाहिए?" : "What would you like help with?"}</h2>
        <p>{hi ? "सामान्य स्वास्थ्य जानकारी पूछें या पोर्टल में मदद लें। यह बातचीत CareVoice द्वारा सेव नहीं की जाती।" : "Ask general health-information questions or get help navigating the portal. Your conversation is not saved by CareVoice."}</p>
        <div className="disclaimer">{hi ? "नाम, संपर्क विवरण या पहचान योग्य स्वास्थ्य जानकारी साझा न करें। तत्काल लक्षणों के लिए आपातकालीन सेवाओं या योग्य चिकित्सक से संपर्क करें।" : "Do not share names, contact details, or other identifying health information. For urgent symptoms, contact local emergency services or a qualified clinician."}</div>
        <div className="disclaimer">{speechConfig?.provider === "browser"
          ? (hi ? "ब्राउज़र की वॉइस पहचान सेवा पर ऑडियो प्रोसेस हो सकता है। भेजने से पहले लिखित रूप की समीक्षा करें।" : "Browser voice recognition may process audio through the browser provider. Review the transcript before sending.")
          : (hi ? "ऑडियो आपके कॉन्फ़िगर किए गए वॉइस प्रदाता को भेजा जाएगा। लिखित रूप समीक्षा के बाद ही भेजें।" : "Audio is sent to the configured speech provider. Review the transcript before sending.")}</div>
      </div>
      <section className="card chat-card" aria-label="CareVoice conversation">
        <div className="chat-messages" aria-live="polite">
          {!messages.length && <p className="chat-empty">{hi ? "आपकी बातचीत यहाँ दिखाई देगी। लिखकर या बोलकर शुरू करें।" : "Your conversation will appear here. Start by typing or using voice input."}</p>}
          {messages.map((message, index) => (
            <article className={`chat-message ${message.role}`} key={`${index}-${message.role}`}>
              <b>{message.role === "user" ? (hi ? "आप" : "You") : "CareVoice"}</b>
              <p>{message.content}</p>
              {message.role === "assistant" && message.citations?.length > 0 && (
                <div className="chat-citations">
                  <b>{hi ? "स्रोत" : "Sources"}</b>
                  <ul>
                    {message.citations.map((citation) => (
                      <li key={`${citation.source_url}-${citation.version}`}>
                        <a href={citation.source_url} target="_blank" rel="noreferrer">{citation.title}</a>
                        <small>{citation.citation} · v{citation.version} · retrieved {new Date(citation.retrieval_date).toLocaleDateString()}</small>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {message.role === "assistant" && <button className="text-button" type="button" onClick={() => speak(message.content)}>🔊 {hi ? "ज़ोर से सुनें" : "Read aloud"}</button>}
            </article>
          ))}
          {transcriptionBusy && <p className="chat-empty" role="status">{hi ? "आवाज़ लिखित रूप में बदली जा रही है…" : "Transcribing audio…"}</p>}
          {busy && <p className="chat-empty" role="status">{hi ? "CareVoice जवाब तैयार कर रहा है…" : "CareVoice is preparing a reply…"}</p>}
        </div>
        <form className="chat-form" onSubmit={sendMessage}>
          {transcriptNeedsConfirmation && <div className="notice" role="status">{hi ? "कृपया ट्रांसक्रिप्ट की समीक्षा करें और पुष्टि करें। आप इसे संपादित कर सकते हैं।" : "Review and confirm the transcript. You can edit it before sending."}<button type="button" onClick={() => setTranscriptNeedsConfirmation(false)}>{hi ? "ट्रांसक्रिप्ट की पुष्टि करें" : "Confirm transcript"}</button></div>}
          {speechConfigError && <p className="chat-empty">{hi ? "वॉइस सेटिंग उपलब्ध नहीं हैं; आप लिखकर जारी रख सकते हैं।" : "Voice settings are unavailable; you can continue by typing."}</p>}
          <textarea aria-label={hi ? "संदेश" : "Message"} value={draft} onChange={(event) => setDraft(event.target.value)} placeholder={hi ? "सामान्य प्रश्न लिखें…" : "Type a general question…"} maxLength={4000} rows={2} />
          <div className="chat-actions">
            <button className="secondary" type="button" onClick={listening ? () => {
              if (mediaRecorderRef.current?.state === "recording") mediaRecorderRef.current.stop();
              else recognitionRef.current?.stop();
            } : startListening} disabled={busy || transcriptionBusy}>
              {listening ? (hi ? "सुनना बंद करें" : "Stop listening") : (hi ? "🎙 बोलकर पूछें" : "🎙 Use voice")}
            </button>
            <button className="primary" type="submit" disabled={busy || transcriptionBusy || transcriptNeedsConfirmation || !draft.trim()}>{busy ? (hi ? "भेज रहे हैं…" : "Sending…") : (hi ? "संदेश भेजें →" : "Send message →")}</button>
          </div>
        </form>
      </section>
    </section>
  );
}
