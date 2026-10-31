import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { BACKEND_BACK, request } from '../api/client';

export interface Profile {
  id: string;
  name: string;
  description: string;
  createdAt: string;
  updatedAt: string;
}

interface ProfileContextType {
  profiles: Profile[];
  activeProfileId: string | null;
  activeProfile: Profile | null;
  isLoading: boolean;
  error: string | null;
  clearError: () => void;
  
  // Profile operations
  loadProfiles: () => Promise<void>;
  createProfile: (id: string, name: string, description?: string) => Promise<Profile | null>;
  deleteProfile: (id: string, force?: boolean) => Promise<boolean>;
  switchProfile: (id: string) => Promise<boolean>;
}

const ProfileContext = createContext<ProfileContextType | undefined>(undefined);

export const useProfile = (): ProfileContextType => {
  const context = useContext(ProfileContext);
  if (!context) {
    throw new Error('useProfile must be used within a ProfileProvider');
  }
  return context;
};

interface ProfileProviderProps {
  children: ReactNode;
}

export const ProfileProvider: React.FC<ProfileProviderProps> = ({ children }) => {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [activeProfileId, setActiveProfileId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Load profiles on mount
  useEffect(() => {
    loadProfiles();
  }, []);

  // No active profile means the first load failed: try again once the backend answers.
  useEffect(() => {
    if (activeProfileId) return;
    window.addEventListener(BACKEND_BACK, loadProfiles);
    return () => window.removeEventListener(BACKEND_BACK, loadProfiles);
  }, [activeProfileId]);

  const loadProfiles = async () => {
    try {
      setIsLoading(true);
      setError(null);
      
      const data = await request<{ profiles: Profile[]; activeProfileId: string | null }>('/api/profiles');
      
      setProfiles(data.profiles || []);
      setActiveProfileId(data.activeProfileId || null);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to load profiles';
      setError(errorMessage);
      console.error('Error loading profiles:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const createProfile = async (
    id: string,
    name: string,
    description: string = ''
  ): Promise<Profile | null> => {
    try {
      setError(null);
      
      const data = await request<{ success: boolean; profile: Profile }>('/api/profiles', {
        method: 'POST',
        body: JSON.stringify({ id, name, description })
      });
      
      if (data.success && data.profile) {
        // Reload profiles to update list
        await loadProfiles();
        return data.profile;
      }
      
      return null;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to create profile';
      setError(errorMessage);
      console.error('Error creating profile:', err);
      return null;
    }
  };

  const deleteProfile = async (id: string, force: boolean = false): Promise<boolean> => {
    try {
      setError(null);
      
      const url = force ? `/api/profiles/${id}?force=true` : `/api/profiles/${id}`;
      const data = await request<{ success: boolean }>(url, {
        method: 'DELETE'
      });
      
      if (data.success) {
        // Reload profiles to update list
        await loadProfiles();
        return true;
      }
      
      return false;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to delete profile';
      setError(errorMessage);
      console.error('Error deleting profile:', err);
      return false;
    }
  };

  const switchProfile = async (id: string): Promise<boolean> => {
    try {
      setError(null);
      
      const data = await request<{ success: boolean; activeProfile: Profile }>(`/api/profiles/${id}/activate`, {
        method: 'POST'
      });
      
      if (data.success && data.activeProfile) {
        setActiveProfileId(data.activeProfile.id);
        
        // Reinitialize everything with the new profile. The packaged app runs from
        // file://, so an absolute path would leave it; the query carries the backend URL.
        window.location.hash = '#/';
        window.location.reload();
        
        return true;
      }
      
      return false;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to switch profile';
      setError(errorMessage);
      console.error('Error switching profile:', err);
      return false;
    }
  };

  const activeProfile = profiles.find(p => p.id === activeProfileId) || null;

  const value: ProfileContextType = {
    profiles,
    activeProfileId,
    activeProfile,
    isLoading,
    error,
    clearError: () => setError(null),
    loadProfiles,
    createProfile,
    deleteProfile,
    switchProfile
  };

  return (
    <ProfileContext.Provider value={value}>
      {children}
    </ProfileContext.Provider>
  );
};
