'use client';

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import settingsStyles from './SettingsPage.module.css';

const AppearanceSettingsPage = memo(() => {
  const t = useTranslations('Settings');
  const [mounted, setMounted] = useState(false);
  const [isVisible, setIsVisible] = useState(false);
  const [themeLight, setThemeLight] = useState(false);
  const [hasBackground, setHasBackground] = useState(false);

  const updateBodyBackgroundImage = useCallback((imageUrl: string | null) => {
    if (imageUrl) {
      document.body.style.backgroundImage = `url(${imageUrl})`;
      document.body.style.backgroundSize = 'cover';
      document.body.style.backgroundPosition = 'center';
      document.body.style.backgroundRepeat = 'no-repeat';
      document.body.style.backgroundAttachment = 'fixed';
    } else {
      document.body.style.backgroundImage = '';
      document.body.style.backgroundSize = '';
      document.body.style.backgroundPosition = '';
      document.body.style.backgroundRepeat = '';
      document.body.style.backgroundAttachment = '';
    }
  }, []);

  const syncFromStorage = useCallback(() => {
    const isDark = document.documentElement.classList.contains('dark');
    const savedDark = localStorage.getItem('theme_dark');
    const savedLight = localStorage.getItem('theme_light');
    const bgImage = isDark ? savedDark : savedLight;
    const light = isDark
      ? localStorage.getItem('theme_light_image') === 'true'
      : localStorage.getItem('theme_light') === 'true';
    if (bgImage) {
      updateBodyBackgroundImage(bgImage);
    } else {
      updateBodyBackgroundImage(null);
    }
    document.body.classList.toggle('theme-light', light);
    setThemeLight(light);
    setHasBackground(!!bgImage);
  }, [updateBodyBackgroundImage]);

  useEffect(() => {
    setMounted(true);
    const timer = setTimeout(() => setIsVisible(true), 300);
    syncFromStorage();
    return () => clearTimeout(timer);
  }, [syncFromStorage]);

  useEffect(() => {
    if (!mounted) return;
    const observer = new MutationObserver(syncFromStorage);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['class'],
    });
    return () => observer.disconnect();
  }, [mounted, syncFromStorage]);

  const handleLightChange = useCallback(() => {
    const isDark = document.documentElement.classList.contains('dark');
    const bgImage = localStorage.getItem('theme_dark');
    if (isDark && bgImage && !document.body.style.backgroundImage) {
      updateBodyBackgroundImage(bgImage);
    }
    const key = isDark ? 'theme_light_image' : 'theme_light';
    const next = !themeLight;
    localStorage.setItem(key, next ? 'true' : 'false');
    document.body.classList.toggle('theme-light', next);
    setThemeLight(next);
  }, [themeLight, updateBodyBackgroundImage]);

  const handleBackgroundChange = useCallback(() => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.onchange = (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (ev) => {
        const result = ev.target?.result as string;
        if (!result) return;
        const isDark = document.documentElement.classList.contains('dark');
        localStorage.setItem(isDark ? 'theme_dark' : 'theme_light', result);
        updateBodyBackgroundImage(result);
        setHasBackground(true);
      };
      reader.readAsDataURL(file);
    };
    input.click();
  }, [updateBodyBackgroundImage]);

  const handleResetBackground = useCallback(() => {
    const isDark = document.documentElement.classList.contains('dark');
    if (isDark) {
      localStorage.removeItem('theme_dark');
    } else {
      localStorage.removeItem('theme_light');
    }
    updateBodyBackgroundImage(null);
    document.body.classList.remove('theme-light');
    localStorage.removeItem('theme_light_image');
    localStorage.removeItem('theme_light');
    setHasBackground(false);
    setThemeLight(false);
  }, [updateBodyBackgroundImage]);

  if (!mounted || !isVisible) return null;

  return (
    <div
      className={cn(
        settingsStyles.settingsPage,
        'flex flex-row w-full overflow-hidden min-h-0',
        'bg-background/95 backdrop-blur-xl'
      )}
    >
      <div className={settingsStyles.settingsContentScroll}>
        <div className={settingsStyles.settingsContentInner}>
          <h1 className={settingsStyles.settingsPageTitle}>{t('Appearance.title')}</h1>

          <section className={settingsStyles.settingsSection}>
            <h2 className={settingsStyles.settingsSectionTitle}>{t('Appearance.backgroundImage')}</h2>
            <div className={settingsStyles.settingsCard}>
              <div className={settingsStyles.settingItem}>
                <div className={settingsStyles.settingInfo}>
                  <label className={settingsStyles.settingLabel}>{t('Appearance.backgroundImage')}</label>
                  <p className={settingsStyles.settingDescription}>{t('Appearance.backgroundImageDesc')}</p>
                </div>
                <div className={settingsStyles.settingControl}>
                  <Button variant="outline" size="sm" onClick={handleBackgroundChange}>
                    {t('Appearance.uploadImage')}
                  </Button>
                  {hasBackground && (
                    <Button variant="ghost" size="sm" onClick={handleResetBackground}>
                      {t('Appearance.resetBackground')}
                    </Button>
                  )}
                </div>
              </div>
              <div className={settingsStyles.settingItem}>
                <div className={settingsStyles.settingInfo}>
                  <label className={settingsStyles.settingLabel}>{t('Appearance.themeLight')}</label>
                  <p className={settingsStyles.settingDescription}>{t('Appearance.themeLightHint')}</p>
                </div>
                <div className={settingsStyles.settingControl}>
                  <label className={settingsStyles.toggle}>
                    <input type="checkbox" checked={themeLight} onChange={handleLightChange} />
                    <span className={settingsStyles.toggleSlider} />
                  </label>
                </div>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
});

AppearanceSettingsPage.displayName = 'AppearanceSettingsPage';
export default AppearanceSettingsPage;
