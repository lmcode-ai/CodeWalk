import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Arrays;

// A1;B1 -- idx=5127007 (bubbleSort) then idx=17335375 (encrypt/SHA-1)
public class Composed1 {

    // idx=5127007
    public static void bubbleSort(int[] a) {
        for (int i = a.length - 1; i > 0; i--) {
            for (int j = 0; j < i; j++) {
                if (a[j] > a[j + 1]) {
                    int tmp = a[j];
                    a[j] = a[j + 1];
                    a[j + 1] = tmp;
                }
            }
        }
    }

    // idx=17335375
    public static byte[] encrypt(String x) throws NoSuchAlgorithmException {
        MessageDigest d = null;
        d = MessageDigest.getInstance("SHA-1");
        d.reset();
        d.update(x.getBytes());
        return d.digest();
    }

    static String toHex(byte[] b) {
        StringBuilder sb = new StringBuilder();
        for (byte x : b) sb.append(String.format("%02x", x));
        return sb.toString();
    }

    public static void main(String[] args) throws Exception {
        int[] arr = {5, 3, 8, 1, 9, 2};
        bubbleSort(arr);
        byte[] digest = encrypt("hello world");
        System.out.println(Arrays.toString(arr));
        System.out.println(toHex(digest));
    }
}
