import java.security.MessageDigest;
import java.util.Arrays;

// A2;B2 -- idx=1668091 (sort) then idx=14333733 (encrypt/SHA-1)
// Expect: same output as Composed1, since (A1,A2) equivalent and (B1,B2) equivalent.
public class Composed2 {

    // idx=1668091
    protected static int[] sort(int[] arr) {
        for (int i = arr.length - 1; i > 0; i--) {
            for (int j = 0; j < i; j++) {
                if (arr[j] > arr[j + 1]) {
                    int temp = arr[j];
                    arr[j] = arr[j + 1];
                    arr[j + 1] = temp;
                }
            }
        }
        return arr;
    }

    // idx=14333733
    public static byte[] encrypt(String x) throws Exception {
        java.security.MessageDigest d = null;
        d = java.security.MessageDigest.getInstance("SHA-1");
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
        int[] sorted = sort(arr);
        byte[] digest = encrypt("hello world");
        System.out.println(Arrays.toString(sorted));
        System.out.println(toHex(digest));
    }
}
