import { useTranslation } from 'react-i18next';
import { Code2, Mail } from 'lucide-react';
import { AboutPanel, HealthMark } from '@neuronection/assistant-ui';
import { PageHeader } from '../../components/ui/PageHeader';
import { useSettingsStore } from '../../store/slices/settingsSlice';

const AboutPage = () => {
  const { t } = useTranslation();
  const theme = useSettingsStore(state => state.theme);
  const logoTheme = theme === 'dark' ? 'dark' : 'light';

  return (
    <div className="w-full max-w-4xl mx-auto pb-20">
      <PageHeader
        title={t('common.about', 'About MediBot')}
        icon={<HealthMark size={24} theme={logoTheme} />}
      />

      <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
        <AboutPanel
          appName="MediBot"
          familyCurrent="health"
          tagline="AI-Powered Personal Health Copilot"
          description="MediBot is an intelligent, bilingual health copilot built to convert messy medical reports and lab tests into structured facts with source provenance. Featuring high-speed LPU inference for English and Hindi summaries, an interactive timeline, FHIR R4 interoperability, and simulated ABHA workflows."
          version="1.0.0"
          license={{
            name: 'Apache License 2.0',
            href: 'https://www.apache.org/licenses/LICENSE-2.0',
          }}
          linksTitle="Project & Team"
          links={[
            {
              group: 'Project',
              href: 'https://github.com/AnshumanPanda1/bytexl-panda-',
              label: 'GitHub Repository',
              subtitle: 'AnshumanPanda1/bytexl-panda-',
              icon: Code2,
            },
            {
              group: 'Team',
              copyValue: 'brahmasmi22@gmail.com',
              label: 'Contact Team',
              subtitle: 'brahmasmi22@gmail.com',
              icon: Mail,
            },
          ]}
          creator={{
            name: 'Anshuman, Tanish & Team',
            role: 'Hackathon Engineering Team',
            href: 'https://github.com/AnshumanPanda1/bytexl-panda-',
          }}
          tech={[
            'FastAPI',
            'Groq LPU Inference (Qwen 27B / Llama 3.1)',
            'PostgreSQL + TimescaleDB',
            'HL7 FHIR R4',
            'React 18 + Vite',
            'Bilingual Summaries (English & Hindi)',
            'Docker Compose',
            'Apache-2.0',
          ]}
          note={{
            tone: 'warning',
            title: 'Medical Disclaimer',
            children:
              'This software is for informational and hackathon demonstration purposes only. It does NOT provide medical diagnosis or act as a substitute for professional medical care. Always consult licensed medical professionals for health advice, diagnoses, or treatment decisions.',
          }}
          copyright="© 2026 MediBot Team"
          theme={logoTheme}
        />
      </div>
    </div>
  );
};

export default AboutPage;
