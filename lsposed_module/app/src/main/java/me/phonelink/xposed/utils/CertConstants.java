package me.phonelink.xposed.utils;

import android.content.pm.Signature;
import android.content.pm.SigningInfo;
import android.os.Build;

import java.lang.reflect.Constructor;

public class CertConstants {
    /**
     * Genuine Samsung Platform / MDX Release Certificate (DER encoded hex).
     * Subject: C=KR, ST=Republic of Korea, L=Suwon City, O=Samsung Electronics Co. Ltd.,
     *          OU=Mobile Communications Business, CN=Samsung Platform Key for IOT devices
     * SHA-256: 2daa022c00fdd426a1590f7601adc7bec9b7f8c302680a4263b54884c576398f
     * Length: 1042 bytes (2084 hex chars)
     */
    public static final String SAMSUNG_MDX_RELEASE_CERT_HEX =
        "3082040e308202f6a0030201020206017ce4114f86300d06092a864886f70d01010505003081bd" +
        "310b3009060355040613024b52311a30180603550408131152657075626c6963206f66204b6f72" +
        "6561311330110603550407130a5375776f6e204369747931253023060355040a131c53616d7375" +
        "6e6720456c656374726f6e69637320436f2e204c74642e31273025060355040b131e4d6f62696c" +
        "6520436f6d6d756e69636174696f6e7320427573696e657373312d302b0603550403132453616d" +
        "73756e6720506c6174666f726d204b657920666f7220494f542064657669636573301e170d3231" +
        "313130333034333135325a170d3431313130323135303030305a3081bd310b3009060355040613" +
        "024b52311a30180603550408131152657075626c6963206f66204b6f7265613113301106035504" +
        "07130a5375776f6e204369747931253023060355040a131c53616d73756e6720456c656374726f" +
        "6e69637320436f2e204c74642e31273025060355040b131e4d6f62696c6520436f6d6d756e6963" +
        "6174696f6e7320427573696e657373312d302b0603550403132453616d73756e6720506c617466" +
        "6f726d204b657920666f7220494f54206465766963657330820122300d06092a864886f70d0101" +
        "0105000382010f003082010a0282010100b59bf685e92c3075041ec8952a511d23ea013c70af11" +
        "5d4aae07307cf86e7a7d9fd253cb405a394ce7767859f576ab7d5202210223e6f2ae2d52a93479" +
        "33fadc9ff3396ffc784b68f2c106f6038a49b779f6221a1e5c1f636e96aacefec6ca460fe54b93" +
        "d41ca6b16583411b6bf8eeae8014f8c46a1101445b9c42c3e2eee893d8c300e3ebab428e77a0d9" +
        "f7acf7992c46649e6b8a206d249fda97978572428b38dbb7d71d715005080b7d3bcbc7280d321d" +
        "299e09c8981eec7699a533049fff0c1c48f152fa16db0d1776dfe31db7735bb53633b6dc8f4b0c" +
        "6effea9152d431ec48dbea09523fe1b0d3e1cb54b9e5e4b107ebae7b9d3b33dd1b77baedd9b059" +
        "0203010001a3123010300e0603551d0f0101ff0404030205a0300d06092a864886f70d01010505" +
        "0003820101006fd7b92f463a1d2f5fc08dd3b06880a12afe76c80dc47f0113f06016de59a77859" +
        "be19515c5b93285acb25e2701d832bef6fc4c489e081cffcd1fb3930420cf757eceb9b1f64cfe0" +
        "ca705b00f73b7d0431aeb616085d3d1b392a41802e144acbf49d841ac9787988915446283d61cb" +
        "4cc25272460a9d0717539f64feacb19042d027b3242f4332ee869f0d8254d514d9824f01b80647" +
        "0a637a124beb66ecf1ade20cbcac371c44b4595e9528c6b43dd3ae967c2d71134425d1684949b1" +
        "3f312b9c48f156c18431fb3d82b6f67bc04be8d1b4cf17042d91a0159471f90672e2f29e181ec1" +
        "06696de357b0c6398031c2806b5e8b4db606ee0d2e718a5a92218281";

    private static volatile Signature sSamsungMdxSignature;

    public static Signature getSamsungMdxSignature() {
        if (sSamsungMdxSignature == null) {
            synchronized (CertConstants.class) {
                if (sSamsungMdxSignature == null) {
                    sSamsungMdxSignature = new Signature(SAMSUNG_MDX_RELEASE_CERT_HEX);
                }
            }
        }
        return sSamsungMdxSignature;
    }

    public static SigningInfo createSigningInfo(Signature signature) {
        if (Build.VERSION.SDK_INT < 28) return null;
        try {
            Class<?> signingDetailsClass;
            if (Build.VERSION.SDK_INT >= 31) {
                try {
                    signingDetailsClass = Class.forName("android.content.pm.SigningDetails");
                } catch (ClassNotFoundException e) {
                    signingDetailsClass = Class.forName("android.content.pm.PackageParser$SigningDetails");
                }
            } else {
                signingDetailsClass = Class.forName("android.content.pm.PackageParser$SigningDetails");
            }

            Constructor<?> detailsCtor = signingDetailsClass.getConstructor(Signature[].class, int.class);
            Object details = detailsCtor.newInstance(new Signature[] { signature }, 2);

            Constructor<SigningInfo> infoCtor = SigningInfo.class.getDeclaredConstructor(signingDetailsClass);
            infoCtor.setAccessible(true);
            return infoCtor.newInstance(details);
        } catch (Throwable t) {
            XposedLog.w("CertConstants", "createSigningInfo reflection fallback: " + t.getMessage());
            return null;
        }
    }
}
