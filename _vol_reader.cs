
using System;
using System.Runtime.InteropServices;

class VolReader {
    static void Main() {
        try {
            var guid = new Guid("{BCDE0395-E52F-467C-8E3D-C57293534E89}");
            var type = Type.GetTypeFromCLSID(guid);
            dynamic dev = Activator.CreateInstance(type);
            
            // eRender=0, eConsole=1
            dynamic speaker = dev.GetDefaultAudioEndpoint(0, 1);
            string name = speaker.FriendlyName;
            
            dynamic epVol = speaker.AudioEndpointVolume;
            float scalar = epVol.MasterVolumeLevelScalar;
            bool mute = epVol.Mute;
            int pct = (int)Math.Round(scalar * 100);
            
            Console.WriteLine(pct.ToString());
            Console.Error.WriteLine(name);
        } catch (Exception ex) {
            Console.Error.WriteLine(ex.GetType().Name + ":" + ex.Message);
            Console.WriteLine("-1");
        }
    }
}
