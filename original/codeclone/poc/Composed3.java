import java.security.MessageDigest;
import java.util.Arrays;

// A2;C -- idx=1668091 (sort) then idx=14878300 (MD5, unclustered -- not a member of
// B's cluster 13771944). C substitutes for B2, same signature (String -> byte[]) and
// same input ("hello world") as B1/B2, so the divergence reflects a genuine same-input
// semantic disagreement rather than a type/signature mismatch (see
// Composed3_typemismatch.java for the earlier, weaker version of this case).
public class Composed3 {

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

    // idx=14878300 (C: unclustered, not equivalent to B1/B2)
    public static byte[] MD5(String input) {
        MessageDigest md5 = null;
        try {
            md5 = MessageDigest.getInstance("MD5");
        } catch (java.security.NoSuchAlgorithmException e) {
            return null;
        }
        md5.update(input.getBytes());
        return md5.digest();
    }

    static String toHex(byte[] b) {
        StringBuilder sb = new StringBuilder();
        for (byte x : b) sb.append(String.format("%02x", x));
        return sb.toString();
    }

    public static void main(String[] args) throws Exception {
        int[] arr = {5, 3, 8, 1, 9, 2};
        int[] sorted = sort(arr);
        byte[] digest = MD5("hello world");
        System.out.println(Arrays.toString(sorted));
        System.out.println(toHex(digest));
    }
}
