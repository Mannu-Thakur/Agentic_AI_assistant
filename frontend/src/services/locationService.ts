/**
 * Real-time Location Service
 * Multi-tiered location detection:
 * 1. HTML5 High-Accuracy Geolocation API -> Reverse geocoding via BigDataCloud & OpenStreetMap Nominatim
 * 2. IP Geolocation via ipwho.is (fast, HTTPS, no CORS restriction)
 * 3. IP Geolocation via BigDataCloud Client Info
 * 4. IP Geolocation via ipapi.co
 */

export async function detectUserLocation(): Promise<string> {
  // 1. Try HTML5 Geolocation API with reverse geocoding
  if (typeof navigator !== 'undefined' && 'geolocation' in navigator) {
    try {
      const pos = await new Promise<GeolocationPosition>((resolve, reject) => {
        navigator.geolocation.getCurrentPosition(resolve, reject, {
          timeout: 6000,
          enableHighAccuracy: true,
          maximumAge: 300000, // 5 min cache
        });
      });
      const { latitude, longitude } = pos.coords;

      // Try BigDataCloud reverse geocode (fast, high-precision)
      try {
        const bdcRes = await fetch(
          `https://api.bigdatacloud.net/data/reverse-geocode-client?latitude=${latitude}&longitude=${longitude}&localityLanguage=en`
        );
        if (bdcRes.ok) {
          const bdcData = await bdcRes.json();
          const city = bdcData.city || bdcData.locality || bdcData.principalSubdivision;
          const region = bdcData.principalSubdivision;
          const country = bdcData.countryName;
          const parts = [city, region, country].filter(Boolean);
          if (parts.length > 0) {
            const result = parts.join(', ');
            localStorage.setItem('omni_user_location', result);
            localStorage.setItem('omni_user_location_timestamp', String(Date.now()));
            return result;
          }
        }
      } catch (_) {}

      // OpenStreetMap Nominatim fallback
      try {
        const res = await fetch(`https://nominatim.openstreetmap.org/reverse?lat=${latitude}&lon=${longitude}&format=json`);
        if (res.ok) {
          const data = await res.json();
          const address = data.address || {};
          const city = address.city || address.town || address.village || address.suburb || address.county;
          const region = address.state;
          const country = address.country;
          const parts = [city, region, country].filter(Boolean);
          if (parts.length > 0) {
            const result = parts.join(', ');
            localStorage.setItem('omni_user_location', result);
            localStorage.setItem('omni_user_location_timestamp', String(Date.now()));
            return result;
          }
        }
      } catch (_) {}
    } catch (e) {
      console.warn('HTML5 Geolocation API unavailable or permission denied, falling back to IP geolocation:', e);
    }
  }

  // Helper for fetch with timeout
  const fetchWithTimeout = async (url: string, timeoutMs: number = 4000): Promise<Response | null> => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const res = await fetch(url, { signal: controller.signal });
      clearTimeout(timer);
      return res;
    } catch {
      clearTimeout(timer);
      return null;
    }
  };

  // 2. IP Geolocation Provider 1: ipwho.is (no CORS issue, HTTPS, free)
  try {
    const ipwhoRes = await fetchWithTimeout('https://ipwho.is/');
    if (ipwhoRes && ipwhoRes.ok) {
      const data = await ipwhoRes.json();
      if (data.success) {
        const parts = [data.city, data.region, data.country].filter(Boolean);
        if (parts.length > 0) {
          const result = parts.join(', ');
          localStorage.setItem('omni_user_location', result);
          localStorage.setItem('omni_user_location_timestamp', String(Date.now()));
          return result;
        }
      }
    }
  } catch (_) {}

  // 3. IP Geolocation Provider 2: BigDataCloud IP Geocode
  try {
    const bdcIpRes = await fetchWithTimeout('https://api.bigdatacloud.net/data/client-info');
    if (bdcIpRes && bdcIpRes.ok) {
      const bdcIpData = await bdcIpRes.json();
      const loc = bdcIpData.location || {};
      const parts = [loc.city, loc.principalSubdivision, loc.countryName].filter(Boolean);
      if (parts.length > 0) {
        const result = parts.join(', ');
        localStorage.setItem('omni_user_location', result);
        localStorage.setItem('omni_user_location_timestamp', String(Date.now()));
        return result;
      }
    }
  } catch (_) {}

  // 4. IP Geolocation Provider 3: ipapi.co
  try {
    const ipRes = await fetchWithTimeout('https://ipapi.co/json/');
    if (ipRes && ipRes.ok) {
      const ipData = await ipRes.json();
      const parts = [ipData.city, ipData.region, ipData.country_name].filter(Boolean);
      if (parts.length > 0) {
        const result = parts.join(', ');
        localStorage.setItem('omni_user_location', result);
        localStorage.setItem('omni_user_location_timestamp', String(Date.now()));
        return result;
      }
    }
  } catch (_) {}

  const cached = localStorage.getItem('omni_user_location');
  if (cached) return cached;

  localStorage.removeItem('omni_user_location');
  return '';
}
